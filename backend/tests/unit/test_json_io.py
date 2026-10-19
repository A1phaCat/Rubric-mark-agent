import json
from pathlib import Path

import pytest

from app.llm.json_io import extract_json, validate_json

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = json.loads(
    (ROOT / "contracts/schemas/report_text.schema.json").read_text(encoding="utf-8")
)


def test_extracts_fenced_json() -> None:
    assert extract_json('```json\n{"value": 1}\n```') == {"value": 1}


def test_extracts_object_from_surrounding_text() -> None:
    assert extract_json('Answer: {"value": 2}.') == {"value": 2}


def test_validates_without_repair() -> None:
    text = '{"summary":"ok","strengths":[],"improvements":[],"next_steps":[]}'
    assert validate_json(text, SCHEMA)["summary"] == "ok"


def test_repairs_exactly_once() -> None:
    calls = []

    def repair(_text: str, error: str) -> str:
        calls.append(error)
        return '{"summary":"fixed","strengths":[],"improvements":[],"next_steps":[]}'

    assert validate_json("not json", SCHEMA, repair)["summary"] == "fixed"
    assert len(calls) == 1


def test_failed_repair_raises() -> None:
    with pytest.raises(ValueError, match="Repair failed"):
        validate_json("bad", SCHEMA, lambda _text, _error: "still bad")
