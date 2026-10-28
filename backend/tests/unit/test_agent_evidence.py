"""The evidence-check agent: verified citations, search before "missing", bounded rounds."""

import asyncio
import json

from app.agent import EvidenceWorkspace, run_evidence_check
from app.agent.loop import SYSTEM_HEADER
from app.grading.service import _normalise_gate
from app.llm.protocol import ChatResponse, ToolCall
from app.retrieval import full_document

DOCUMENT = {"paragraphs": [
    {"kind": "heading", "text": "3 Evaluation", "page": 2, "label": ""},
    {"kind": "paragraph", "text": "We compare the tracker against a manual paper log used in two kitchens.", "page": 2, "label": "¶1"},
    {"kind": "paragraph", "text": "Over four weeks, logged waste fell by 18% in the tracker kitchen.", "page": 2, "label": "¶2"},
    {"kind": "heading", "text": "Appendix C", "page": 9, "label": ""},
    {"kind": "paragraph", "text": "Known failure: items thrown away without being scanned are missed.", "page": 9, "label": "¶3"},
]}
ASPECTS = [{"id": "baseline", "label": "Compares against a baseline"},
           {"id": "metrics", "label": "Reports quantitative results"},
           {"id": "failures", "label": "Analyses failure cases"}]
CRITERION = {"id": "crt_e", "name": "Evaluation", "weight": 4, "grading_mode": "analytic", "aspects":
             [{**a, "source": "explicit"} for a in ASPECTS],
             "levels": [{"label": "Exceeds", "points": 4, "description": ""}, {"label": "Below", "points": 0, "description": ""}]}


def call(name: str, **arguments) -> ToolCall:
    return ToolCall(id=f"{name}_{len(arguments)}", name=name, raw_arguments=json.dumps(arguments), arguments=arguments)


class Scripted:
    """Plays back one turn per call and records the conversation it was sent."""

    def __init__(self, *turns: tuple[ToolCall, ...]) -> None:
        self.turns = list(turns)
        self.sent: list[list[dict]] = []

    async def chat(self, *, purpose, messages, tools, metadata=None):
        self.sent.append([dict(m) for m in messages])
        calls = self.turns.pop(0) if self.turns else (call("finish", notes="out of script"),)
        return ChatResponse(text="", tool_calls=tuple(calls), model="scripted", input_tokens=100, cached_tokens=80)


def _run(llm, **kwargs):
    full = full_document(DOCUMENT)
    return asyncio.run(run_evidence_check(llm, full, "{brief}", ASPECTS, max_citations=8, **kwargs))


def test_the_model_reads_the_whole_submission_first() -> None:
    llm = Scripted((call("finish", notes="none"),), (call("finish", notes="none"),))
    _run(llm)
    system = llm.sent[0][0]["content"]
    assert system.startswith(SYSTEM_HEADER)
    assert "Known failure: items thrown away" in system  # appendix included, nothing is chosen for it
    assert "ASPECT IDS: baseline, metrics, failures" in llm.sent[0][1]["content"]


def test_an_invented_quote_is_rejected_on_the_spot_and_can_be_corrected() -> None:
    llm = Scripted(
        (call("cite", paragraph_id="p2", quote="waste fell by 25%", aspect_ids=["metrics"], relevance="direct"),),
        (call("cite", paragraph_id="p2", quote="logged waste fell by 18%", aspect_ids=["metrics"], relevance="direct"),
         call("cite", paragraph_id="p1", quote="We compare the tracker against a manual paper log", aspect_ids=["baseline"], relevance="direct"),
         call("cite", paragraph_id="p3", quote="items thrown away without being scanned are missed", aspect_ids=["failures"], relevance="direct")),
        (call("finish", notes="all found"),),
    )
    check = _run(llm)
    tool_reply = llm.sent[1][-1]
    assert tool_reply["role"] == "tool" and tool_reply["content"].startswith("invalid")
    assert [e["quote"] for e in check.gate_raw["evidence"]] == [
        "logged waste fell by 18%", "We compare the tracker against a manual paper log",
        "items thrown away without being scanned are missed"]
    assert check.finished and check.rounds == 3
    assert [s.outcome for s in check.steps if s.tool == "cite"] == ["invalid", "valid", "valid", "valid"]


def test_missing_is_only_accepted_after_a_search() -> None:
    llm = Scripted(
        (call("cite", paragraph_id="p1", quote="We compare the tracker against a manual paper log", aspect_ids=["baseline"], relevance="direct"),
         call("cite", paragraph_id="p2", quote="logged waste fell by 18%", aspect_ids=["metrics"], relevance="direct")),
        (call("finish", notes="failures not addressed"),),            # too early: nudged
        (call("search", query="failure scanned missed", aspect_ids=["failures"]),),
        (call("cite", paragraph_id="p3", quote="items thrown away without being scanned are missed", aspect_ids=["failures"], relevance="direct"),
         call("finish", notes="found in the appendix")),
    )
    check = _run(llm)
    assert [s.kind for s in check.steps if s.kind == "nudge"] == ["nudge"]
    assert [s.outcome for s in check.steps if s.tool == "finish"] == ["deferred", "done"]
    assert "Before finishing, search" in llm.sent[2][-1]["content"]
    assert "[p3 | p.9 ¶3]" in llm.sent[3][-1]["content"]  # the search found the appendix paragraph
    assert {a for e in check.gate_raw["evidence"] for a in e["aspect_ids"]} == {"baseline", "metrics", "failures"}
    assert check.finished and check.gate_raw["notes"] == "found in the appendix"


def test_a_searched_aspect_can_be_reported_missing() -> None:
    llm = Scripted(
        (call("search", query="reproducibility random seed", aspect_ids=["failures"]),),
        (call("finish", notes="no failure analysis"),),
    )
    workspace_steps = _run(llm).steps
    assert not [s for s in workspace_steps if s.kind == "nudge" and "failures" in s.detail]


def test_rounds_are_bounded() -> None:
    endless = tuple((call("search", query="baseline"),) for _ in range(20))
    check = _run(Scripted(*endless), max_rounds=3)
    assert check.rounds == 3 and not check.finished
    assert check.steps[-1].kind == "limit"


def test_the_same_quote_for_two_aspects_is_one_piece_of_evidence() -> None:
    workspace = EvidenceWorkspace(full_document(DOCUMENT), ASPECTS, 8)
    workspace.cite({"paragraph_id": "p2", "quote": "logged waste fell by 18%", "aspect_ids": ["metrics"]})
    outcome = workspace.cite({"paragraph_id": "p2", "quote": "Logged waste fell by 18%", "aspect_ids": ["baseline"]})
    assert outcome.outcome == "merged"
    assert [c.aspect_ids for c in workspace.citations] == [["metrics", "baseline"]]


def test_right_words_with_the_wrong_paragraph_id_are_moved() -> None:
    workspace = EvidenceWorkspace(full_document(DOCUMENT), ASPECTS, 8)
    outcome = workspace.cite({"paragraph_id": "p1", "quote": "logged waste fell by 18%", "aspect_ids": ["metrics"]})
    assert outcome.outcome == "relocated" and workspace.citations[0].passage_id == "p2"


def test_bad_arguments_get_a_useful_error() -> None:
    workspace = EvidenceWorkspace(full_document(DOCUMENT), ASPECTS, 8)
    assert workspace.run("cite", None).reply.startswith("error: the arguments were not valid JSON")
    assert "baseline, metrics, failures" in workspace.run("cite", {"quote": "x", "aspect_ids": ["nope"]}).reply
    assert workspace.run("delete_everything", {}).outcome == "error"


def test_output_feeds_the_existing_evidence_gate_unchanged() -> None:
    llm = Scripted(
        (call("cite", paragraph_id="p1", quote="We compare the tracker against a manual paper log", aspect_ids=["baseline"], relevance="direct"),
         call("search", query="failures", aspect_ids=["failures", "metrics"]),),
        (call("finish", notes="partial"),),
    )
    check = _run(llm)
    full = full_document(DOCUMENT)
    gate = _normalise_gate(CRITERION, full.passages, check.gate_raw, max_items=8)
    assert [e["passage_id"] for e in gate["evidence"]] == ["p1"]
    assert {c["aspect_id"]: c["status"] for c in gate["coverage"]} == {
        "baseline": "supported", "metrics": "missing", "failures": "missing"}


def test_token_use_is_totalled_and_the_cache_warm_up_hook_fires_once() -> None:
    fired = []
    llm = Scripted((call("search", query="baseline", aspect_ids=["baseline", "metrics", "failures"]),),
                   (call("finish", notes="x"),))
    check = _run(llm, after_first_turn=lambda: fired.append(1))
    assert fired == [1]
    assert (check.input_tokens, check.cached_tokens) == (200, 160)
