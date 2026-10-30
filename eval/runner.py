"""Run every case under each condition and variant; one JSON line per graded criterion.

Conditions differ only in how the evidence is found; the grade step and the rules after it
are the product's own:

- ``direct``: the whole submission and the criterion in one call, no evidence step (baseline)
- ``retrieval``: evidence chosen from the passages retrieved for each criterion
- ``full``: evidence chosen from the whole submission in one call
- ``full_tools``: the whole submission, quotes verified as they are cited, search before
  "missing" (the product default)

Results are appended as they arrive, so an interrupted run resumes where it stopped.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.config import Settings
from app.domain import levels
from app.grading import grade_criterion
from app.grading.baseline import grade_directly
from app.retrieval import full_document, retrieve_passages

from . import variants
from .dataset import Case, case_document, criteria, document, load_rubric

CONDITIONS = ("direct", "retrieval", "full", "full_tools")
VARIANTS = ("original", "injected", "truncated", "decoy", "removed")
EVIDENCE_CONDITIONS = ("retrieval", "full", "full_tools")
_PROMPT_RESERVE_TOKENS = 12_000
_OUTPUT_ATTEMPTS = 2


@dataclass
class Unit:
    """One submission version graded under one condition: its criteria share a cached prefix."""

    case: Case
    variant: str
    condition: str
    repeat: int
    document: dict[str, Any]
    criteria: list[dict[str, Any]]
    note: dict[str, Any] = field(default_factory=dict)

    @property
    def submission_id(self) -> str:
        return f"eval-{self.case.id}-{self.variant}-{self.note.get('criterion_removed', 'all')}"


def result_key(case: str, variant: str, condition: str, repeat: int, criterion: str) -> str:
    return f"{case}/{variant}/{condition}/{repeat}/{criterion}"


def read_results(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _trace_summary(trace: list[dict[str, Any]] | None) -> dict[str, Any]:
    steps = trace or []
    tools = [step for step in steps if step.get("kind") == "tool"]
    return {
        "rounds": sum(1 for step in steps if step.get("kind") == "model"),
        "cited": sum(1 for step in tools if step.get("tool") == "cite"),
        "invalid": sum(1 for step in tools if step.get("tool") == "cite" and step.get("outcome") == "invalid"),
        "relocated": sum(1 for step in tools if step.get("outcome") == "relocated"),
        "searches": sum(1 for step in tools if step.get("tool") == "search"),
        "nudged": any(step.get("kind") == "nudge" for step in steps),
        "limit": any(step.get("kind") == "limit" for step in steps),
        "fallback": any(step.get("kind") == "fallback" for step in steps),
    }


def _record(unit: Unit, criterion: dict[str, Any], result: dict[str, Any] | None, error: str, seconds: float) -> dict[str, Any]:
    base = {
        "key": result_key(unit.case.id, unit.variant, unit.condition, unit.repeat, criterion["id"]),
        "case": unit.case.id,
        "rubric": unit.case.rubric,
        "variant": unit.variant,
        "condition": unit.condition,
        "repeat": unit.repeat,
        "criterion": criterion["id"],
        "maximum": float(criterion["weight"]),
        "kind": criterion.get("kind", "content"),
        "levels": len(criterion["levels"]),
        "ok": result is not None,
        "error": error,
        "wall_seconds": round(seconds, 2),
        **unit.note,
    }
    if result is None:
        return base
    score = float(result.get("score") or 0)
    level = levels.level_for(criterion["levels"], score)
    position, _ = levels.rank(criterion["levels"], level)
    evidence = [{"passage_id": item.get("passage_id"), "quote": item.get("quote"),
                 "relevance": item.get("relevance")} for item in result.get("evidence") or []]
    note = [item for item in evidence if variants.cites_injection([item])]
    return {
        **base,
        "score": score,
        "normalised": round(score / base["maximum"], 4) if base["maximum"] else 0.0,
        "level": result.get("level"),
        "level_rank": position,  # 0 = best level
        "confidence": result.get("confidence"),
        "context_used": result.get("context", unit.condition),
        "sufficiency": result.get("sufficiency"),
        "coverage_ratio": result.get("coverage_ratio"),
        "missing_aspects": result.get("missing_aspects", []),
        "coverage": [{"aspect_id": row.get("aspect_id"), "status": row.get("status")}
                     for row in result.get("coverage") or [] if isinstance(row, dict)],
        "evidence": evidence,
        "evidence_proposed": result.get("evidence_proposed"),
        "injection_cited_as": (
            "support" if any(item["relevance"] != "contradictory" for item in note)
            else "flaw" if note else None
        ),
        "trace": _trace_summary(result.get("evidence_trace")),
        "calls": len(result.get("llm_calls") or []),
        "input_tokens": int(result.get("input_tokens") or 0),
        "output_tokens": int(result.get("output_tokens") or 0),
        "cached_tokens": int(result.get("cached_tokens") or 0),
        "latency_ms": int(result.get("latency_ms") or 0),
        "model": result.get("model"),
        "rationale": result.get("rationale"),
    }


class Runner:
    def __init__(self, settings: Settings, results: Path, *, parallel: int, log: Callable[[str], None] = print) -> None:
        self.settings = settings
        self.results = results
        self.limit = asyncio.Semaphore(parallel)
        self.embedding = asyncio.Lock()
        self.log = log
        self.done = {row["key"] for row in read_results(results) if row.get("ok")}
        self.completed = 0
        self.failed = 0
        self.total = 0

    # ------------------------------------------------------------------ grading
    async def _grade(self, unit: Unit, criterion: dict[str, Any], after_gate: Callable[[], None]) -> dict[str, Any]:
        full = full_document(unit.document)
        if full.estimated_tokens > self.settings.ai_context_tokens - _PROMPT_RESERVE_TOKENS:
            raise RuntimeError(f"too_long: about {full.estimated_tokens} tokens")
        metadata = {"submission_id": unit.submission_id, "criterion_id": criterion["id"]}
        if unit.condition == "direct":
            try:
                return await grade_directly(self.settings, criterion, full, metadata)
            finally:
                after_gate()
        if unit.condition == "retrieval":
            async with self.embedding:  # one embedding model, used by one thread at a time
                passages = await asyncio.to_thread(
                    retrieve_passages, unit.document, criterion, limit=self.settings.retrieval_candidate_limit,
                    settings=self.settings, submission_id=unit.submission_id, document_version=1,
                )
            return await grade_criterion(self.settings.model_copy(update={"grading_context": "retrieval"}),
                                         criterion, passages, metadata, after_gate=after_gate)
        return await grade_criterion(self.settings.model_copy(update={"grading_context": unit.condition}),
                                     criterion, full.passages, metadata, full=full, after_gate=after_gate)

    async def _one(self, unit: Unit, criterion: dict[str, Any], after_gate: Callable[[], None]) -> None:
        started = time.perf_counter()
        result, error = None, ""
        async with self.limit:
            for attempt in range(1, _OUTPUT_ATTEMPTS + 1):
                try:
                    result = await self._grade(unit, criterion, after_gate)
                    break
                except ValueError as exc:  # output that is not valid JSON or does not match the text
                    error = f"{type(exc).__name__}: {exc}"
                    if attempt == _OUTPUT_ATTEMPTS:
                        break
                except Exception as exc:  # recorded and counted; the run carries on
                    error = f"{type(exc).__name__}: {exc}"
                    break
        after_gate()
        row = _record(unit, criterion, result, "" if result is not None else error, time.perf_counter() - started)
        with self.results.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        self.completed += 1
        self.failed += 0 if row["ok"] else 1
        if self.completed % max(10, self.total // 40) == 0 or not row["ok"] or self.completed == self.total:
            status = "" if row["ok"] else f"  FAILED {row['key']}: {error[:160]}"
            self.log(f"  {self.completed}/{self.total} graded, {self.failed} failed{status}")

    async def _unit(self, unit: Unit) -> None:
        todo = [c for c in unit.criteria if result_key(unit.case.id, unit.variant, unit.condition, unit.repeat, c["id"]) not in self.done]
        if not todo:
            return
        warm = asyncio.Event()
        first, rest = todo[0], todo[1:]

        async def later(criterion: dict[str, Any]) -> None:
            await warm.wait()  # as in the product: the first criterion primes the provider cache
            await self._one(unit, criterion, lambda: None)

        await asyncio.gather(self._one(unit, first, warm.set), *(later(c) for c in rest))

    async def run(self, units: list[Unit]) -> None:
        self.total = sum(
            1 for unit in units for c in unit.criteria
            if result_key(unit.case.id, unit.variant, unit.condition, unit.repeat, c["id"]) not in self.done
        )
        if self.total:
            self.log(f"  {self.total} criterion gradings to run ({len(self.done)} already done)")
        await asyncio.gather(*(self._unit(unit) for unit in units))


def plan(
    cases: list[Case],
    *,
    decoys: list[Case],
    conditions: list[str],
    variant_names: list[str],
    repeats: int,
    repeat_per_rubric: int,
) -> list[Unit]:
    """Units that need no earlier results: every variant except ``removed``."""

    units: list[Unit] = []
    seen: dict[str, int] = defaultdict(int)
    for index, case in enumerate(cases):
        position = seen[case.rubric]
        seen[case.rubric] += 1
        rubric_criteria = criteria(load_rubric(case.rubric))
        original = case_document(case)
        for variant in variant_names:
            if variant == "removed":
                continue
            if variant == "decoy":
                if not decoys:
                    continue
                other = decoys[index % len(decoys)]
                version, note = document(f"eval-{case.id}-decoy", other.text), {"decoy": other.id}
            elif variant == "injected":
                version, note = variants.injected(original), {}
            elif variant == "truncated":
                version, note = variants.truncated(original), {}
            else:
                version, note = original, {}
            for condition in conditions:
                rounds = repeats if variant == "original" and position < repeat_per_rubric else 1
                for repeat in range(rounds):
                    units.append(Unit(case, variant, condition, repeat, version, rubric_criteria, dict(note)))
    return units


def removal_plan(cases: list[Case], conditions: list[str], rows: list[dict[str, Any]], per_case: int) -> list[Unit]:
    """Delete the paragraphs cited for a case's heaviest criteria and grade those criteria again.

    The deleted paragraphs are everything any evidence-based condition cited for that
    criterion on the original submission, so every condition loses the same text.
    """

    cited: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in rows:
        if row.get("ok") and row["variant"] == "original" and row["repeat"] == 0 and row["condition"] in EVIDENCE_CONDITIONS:
            cited[(row["case"], row["criterion"])].update(item["quote"] for item in row.get("evidence") or [])
    units: list[Unit] = []
    for case in cases:
        rubric_criteria = criteria(load_rubric(case.rubric))
        heaviest = sorted(rubric_criteria, key=lambda c: (-c["weight"], c["id"]))[:per_case]
        original = case_document(case)
        for criterion in heaviest:
            quotes = cited.get((case.id, criterion["id"]))
            if not quotes:
                continue
            version, dropped = variants.removed(original, quotes)
            note = {"criterion_removed": criterion["id"], "paragraphs_removed": dropped}
            for condition in conditions:
                units.append(Unit(case, "removed", condition, 0, version, [criterion], dict(note)))
    return units
