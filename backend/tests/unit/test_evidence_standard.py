"""Which standard a criterion uses, how aspect answers fill the coverage matrix, and how deductions cap."""

from app.grading.service import _normalise_gate
from app.retrieval import full_document
from app.rubric.assessment import evidence_standard
from tests.unit.test_full_text_grading import ScriptedLLM, _criterion, _document, _run_criterion

MEASURED = {"passage_id": "p4", "quote": "We measured latency under load", "role": "primary",
            "relevance": "direct", "aspect_ids": ["measures", "reports"]}


def _answer(aspect: str, addressed: bool = True, meets: bool = True) -> dict:
    return {"aspect_id": aspect, "addressed": addressed, "meets_standard": meets, "reason": f"{aspect} reason"}


def _gate(raw: dict, **criterion) -> dict:
    full = full_document(_document())
    return _normalise_gate({**_criterion(), **criterion}, full.passages, raw, max_items=8)


def _status(gate: dict) -> dict:
    return {row["aspect_id"]: row["status"] for row in gate["coverage"]}


# ---------------------------------------------------------------- which standard
def test_criteria_need_the_described_standard_by_default() -> None:
    assert evidence_standard({**_criterion(), "weight_share": 0.3}) == "quality"


def test_two_level_and_minor_criteria_only_need_to_be_addressed() -> None:
    binary = {"name": "Submitted on time", "weight": 1, "levels": [
        {"label": "Met", "points": 1, "description": ""}, {"label": "Not met", "points": 0, "description": ""}]}
    assert evidence_standard(binary) == "presence"
    assert evidence_standard({**_criterion(), "weight_share": 0.05}) == "presence"


def test_a_tutors_choice_wins() -> None:
    assert evidence_standard({**_criterion(), "weight_share": 0.02, "evidence_standard": "quality"}) == "quality"
    assert evidence_standard({**_criterion(), "evidence_standard": "presence"}) == "presence"


# ---------------------------------------------------------------- the matrix
def test_addressed_but_below_the_standard_is_partial() -> None:
    raw = {"evidence": [MEASURED], "aspects": [_answer("measures"), _answer("reports", meets=False)]}
    gate = _gate(raw)
    assert _status(gate) == {"measures": "supported", "reports": "partial"}
    assert gate["sufficiency"] == "partial" and gate["evidence_standard"] == "quality"
    reports = next(row for row in gate["coverage"] if row["aspect_id"] == "reports")
    assert reports["meets_standard"] is False and reports["reason"] == "reports reason"


def test_under_the_presence_standard_addressing_it_is_enough() -> None:
    raw = {"evidence": [MEASURED], "aspects": [_answer("measures", meets=False), _answer("reports", meets=False)]}
    gate = _gate(raw, evidence_standard="presence")
    assert _status(gate) == {"measures": "supported", "reports": "supported"}
    assert gate["sufficiency"] == "sufficient"


def test_answers_never_raise_a_status() -> None:
    raw = {"evidence": [], "aspects": [_answer("measures"), _answer("reports")]}
    assert _status(_gate(raw)) == {"measures": "missing", "reports": "missing"}


def test_evidence_the_model_itself_calls_unaddressed_is_partial() -> None:
    raw = {"evidence": [MEASURED], "aspects": [_answer("measures", addressed=False), _answer("reports")]}
    assert _status(_gate(raw, evidence_standard="presence"))["measures"] == "partial"


def test_without_answers_the_evidence_decides_and_the_gap_is_counted() -> None:
    gate = _gate({"evidence": [MEASURED], "aspects": [_answer("measures", meets=False)]})
    assert _status(gate) == {"measures": "partial", "reports": "supported"}
    assert gate["answers_missing"] == 1


# ---------------------------------------------------------------- deductions
FULL = {"score": 10, "level": "Good", "rationale": "Measured and reported.", "confidence": "high"}


def _graded(deductions: list, **criterion) -> dict:
    llm = ScriptedLLM({"evidence": [MEASURED]}, {**FULL, "deductions": deductions})
    return _run_criterion(llm, {**_criterion(), **criterion}), llm


def test_a_material_deduction_holds_the_mark_below_the_best_level() -> None:
    result, llm = _graded([{"aspect_id": "reports", "severity": "material",
                            "issue": "Results are stated without numbers.", "evidence": "p.2 ¶4"}])
    assert (result["score"], result["level"], result["capped"]) == (5, "Fair", "deduction")
    assert result["deductions"][0]["issue"] == "Results are stated without numbers."
    assert "deductions decided before the level" in llm.prompts[1][1]


def test_minor_deductions_leave_the_best_level_reachable() -> None:
    result, _ = _graded([{"aspect_id": "reports", "severity": "minor", "issue": "Could add units.",
                          "evidence": "absent"}])
    assert (result["score"], result["level"]) == (10, "Good") and "capped" not in result


def test_under_the_presence_standard_deductions_are_shown_but_do_not_cap() -> None:
    result, _ = _graded([{"aspect_id": "reports", "severity": "material", "issue": "Thin.", "evidence": "absent"}],
                        evidence_standard="presence")
    assert result["score"] == 10 and result["deductions"]


def test_deductions_must_point_at_shown_evidence_or_an_absence() -> None:
    result, _ = _graded([
        {"aspect_id": "reports", "severity": "material", "issue": "Invented.", "evidence": "p.9 ¶99"},
        {"aspect_id": "nope", "severity": "material", "issue": "Unknown aspect.", "evidence": "absent"},
        {"aspect_id": "reports", "severity": "fatal", "issue": "Unknown severity.", "evidence": "absent"},
    ])
    assert result["deductions"] == [] and result["score"] == 10
