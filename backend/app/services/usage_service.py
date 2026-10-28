"""Token use and cost of a batch: per call, per submission and for the whole batch.

Costs are recomputed from the recorded token counts with the current price table, so a
corrected price applies to past runs too. Calls to models missing from the table are
counted as *unpriced*; their cost is never reported as 0.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.batch import Batch
from app.db.models.llm import LLMCall
from app.db.models.submission import Submission
from app.llm.pricing import PriceTable, load_table


def _money(value: Optional[float]) -> Optional[float]:
    return None if value is None else round(value, 6)


def _empty() -> Dict[str, Any]:
    return {
        "calls": 0,
        "priced_calls": 0,
        "unpriced_calls": 0,
        "input_tokens": 0,
        "cached_tokens": 0,
        "output_tokens": 0,
        "cost_usd": 0.0,
    }


def _add(bucket: Dict[str, Any], call: LLMCall, cost: Optional[float]) -> None:
    bucket["calls"] += 1
    bucket["input_tokens"] += int(call.input_tokens or 0)
    bucket["cached_tokens"] += int(call.cached_tokens or 0)
    bucket["output_tokens"] += int(call.output_tokens or 0)
    if cost is None:
        bucket["unpriced_calls"] += 1
    else:
        bucket["priced_calls"] += 1
        bucket["cost_usd"] += cost


def _finish(bucket: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(bucket)
    # A total that leaves out unpriced calls would understate the spend, so it is withheld.
    out["cost_usd"] = None if bucket["unpriced_calls"] else _money(bucket["cost_usd"])
    out["priced_cost_usd"] = _money(bucket["cost_usd"])
    return out


def batch_usage(
    session: Session,
    batch_id: str,
    *,
    include_calls: bool = False,
    table: Optional[PriceTable] = None,
) -> Dict[str, Any]:
    if session.get(Batch, batch_id) is None:
        raise KeyError(batch_id)
    table = table or load_table()
    rows = session.execute(
        select(LLMCall, Submission.sid, Submission.id)
        .join(Submission, Submission.id == LLMCall.submission_id)
        .where(Submission.batch_id == batch_id)
        .order_by(LLMCall.created_at, LLMCall.id)
    ).all()

    totals = _empty()
    by_model: Dict[str, Dict[str, Any]] = {}
    by_purpose: Dict[str, Dict[str, Any]] = {}
    by_submission: Dict[str, Dict[str, Any]] = {}
    calls: List[Dict[str, Any]] = []
    latency_ms = 0
    for call, sid, submission_id in rows:
        cost = table.cost(call.model, call.input_tokens, call.output_tokens, call.cached_tokens)
        _add(totals, call, cost)
        latency_ms += int(call.latency_ms or 0)
        model = by_model.setdefault(call.model, {"model": call.model, **_empty()})
        _add(model, call, cost)
        purpose = by_purpose.setdefault(call.purpose, {"purpose": call.purpose, **_empty()})
        _add(purpose, call, cost)
        submission = by_submission.setdefault(
            submission_id, {"submission_id": submission_id, "sid": sid, **_empty()}
        )
        _add(submission, call, cost)
        if include_calls:
            calls.append(
                {
                    "id": call.id,
                    "submission_id": submission_id,
                    "provider": call.provider,
                    "model": call.model,
                    "purpose": call.purpose,
                    "input_tokens": call.input_tokens,
                    "cached_tokens": call.cached_tokens,
                    "output_tokens": call.output_tokens,
                    "latency_ms": call.latency_ms,
                    "cost_usd": _money(cost),
                    "created_at": call.created_at.isoformat() if call.created_at else None,
                }
            )

    submissions = [_finish(item) for item in by_submission.values()]
    priced_subs = [item["cost_usd"] for item in submissions if item["cost_usd"] is not None]
    summary = _finish(totals)
    count = len(submissions)
    summary.update(
        {
            "submissions_with_calls": count,
            "latency_ms": latency_ms,
            "cost_per_submission_usd": _money(summary["cost_usd"] / count)
            if summary["cost_usd"] is not None and count
            else None,
            "max_submission_cost_usd": _money(max(priced_subs)) if priced_subs else None,
            "cost_per_call_usd": _money(summary["cost_usd"] / totals["calls"])
            if summary["cost_usd"] is not None and totals["calls"]
            else None,
            "tokens_per_submission": round(
                (totals["input_tokens"] + totals["output_tokens"]) / count
            )
            if count
            else None,
        }
    )
    unpriced = sorted({m for m, item in by_model.items() if item["unpriced_calls"]})
    result: Dict[str, Any] = {
        "batch_id": batch_id,
        "pricing": {**table.describe(), "unpriced_models": unpriced},
        "totals": summary,
        "by_model": [_finish(item) for item in by_model.values()],
        "by_purpose": [_finish(item) for item in by_purpose.values()],
        "submissions": submissions,
    }
    if include_calls:
        result["calls"] = calls
    return result
