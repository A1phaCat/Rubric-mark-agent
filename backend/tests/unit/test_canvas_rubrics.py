"""Real Canvas rubric exports: own level scales, HTML text, label-only levels."""

import json

import pytest

from app.domain.levels import level_for, rank
from app.grading.service import _reconcile_level, _scale_note
from app.rubric.parser import parse_rubric_text
from app.sample.seed import RUBRIC_FILES

CANVAS = sorted(
    path for path in RUBRIC_FILES.glob("*.json")
    if isinstance(json.loads(path.read_text(encoding="utf-8")).get("rubric"), list)
)


def _parse(name: str) -> dict:
    return parse_rubric_text((RUBRIC_FILES / name).read_text(encoding="utf-8"), name)


@pytest.mark.parametrize("path", CANVAS, ids=lambda path: path.stem)
def test_canvas_exports_parse_without_problems(path) -> None:
    raw = json.loads(path.read_text(encoding="utf-8"))
    parsed = parse_rubric_text(path.read_text(encoding="utf-8"), path.name)
    assert [w for w in parsed["warnings"] if w["severity"] != "info"] == []
    assert parsed["title"] == raw["assignment"]["rubric_settings"]["title"]
    assert parsed["source"].startswith("Canvas · ")
    assert [c["name"] for c in parsed["criteria"]] == [" ".join(c["description"].split()) for c in raw["rubric"]]
    for criterion, source in zip(parsed["criteria"], raw["rubric"]):
        assert [level["label"] for level in criterion["levels"]] == [r["description"] for r in source["ratings"]]
        text = criterion["description"] + "".join(level["description"] for level in criterion["levels"])
        assert "<br" not in text and "&#39;" not in text and "&amp;" not in text


def test_each_criterion_keeps_its_own_scale() -> None:
    scope = _parse("capstone-scope.json")
    labels = [[level["label"] for level in c["levels"]] for c in scope["criteria"]]
    assert labels[0] == ["HD", "DI", "CR", "PS", "FL"]
    assert labels[4] == ["HD", "DI", "CR", "PS", "FL", "No Marks"]
    assert labels[5] == ["Exceeds", "Mastery", "Near", "Below"]
    asgn = _parse("comp5348-asgn2.json")
    assert {tuple(level["label"] for level in c["levels"]) for c in asgn["criteria"]} == {
        ("Full credit", "Partial credit", "No credit")
    }


def test_canvas_ratings_are_bands_and_scores_land_in_the_right_one() -> None:
    levels = _parse("capstone-scope.json")["criteria"][0]["levels"]  # 5 / 3.99 / 3 / 1.99 / 0.99
    assert [(level["min_score"], level["max_score"]) for level in levels][:2] == [(3.99, 5.0), (3.0, 3.99)]
    assert [level_for(levels, s)["label"] for s in (5, 4, 3.99, 3.5, 3, 1, 0)] == ["HD", "HD", "DI", "DI", "CR", "PS", "FL"]
    credit = _parse("comp5348-asgn1.json")["criteria"][0]["levels"]
    assert [level_for(credit, s)["label"] for s in (1, 0.75, 0.5, 0)] == ["Full credit", "Full credit", "Partial credit", "No credit"]
    assert rank(credit, level_for(credit, 0.5)) == (1, 3)


def test_label_only_levels_are_valid_and_explained_to_the_model() -> None:
    parsed = _parse("elec5623-final-report.json")
    codes = {w["code"] for w in parsed["warnings"]}
    assert codes == {"levels_without_descriptors"}
    criterion = parsed["criteria"][0]
    assert criterion["description"].startswith("A functional and coherent MVP")
    assert "labels and points only" in _scale_note(criterion)
    assert _scale_note(_parse("capstone-scope.json")["criteria"][0]) == ""


def test_the_stored_level_always_matches_the_score() -> None:
    criterion = _parse("elec5623-final-report.json")["criteria"][3]  # Excellent 3 / Great 2 / Below Average 1 / No Evidence 0
    result = {"score": 2, "level": "Excellent"}
    _reconcile_level(criterion, result)
    assert result["level"] == "Great"
    result = {"score": 9, "level": "Excellent"}
    _reconcile_level(criterion, result)
    assert result == {"score": 3.0, "level": "Excellent"}


def test_partly_described_levels_are_still_flagged() -> None:
    text = json.dumps({"criteria": [{"name": "A", "weight": 2, "levels": [
        {"label": "Good", "points": 2, "description": "Clear"}, {"label": "Poor", "points": 0, "description": ""}]}]})
    warnings = parse_rubric_text(text, "x.json")["warnings"]
    assert [(w["code"], w["severity"]) for w in warnings] == [("level_missing_descriptor", "warning")]
