import json
from collections import Counter
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, RefResolver

ROOT = Path(__file__).resolve().parents[3]
SPEC = yaml.safe_load((ROOT / "contracts/openapi.yaml").read_text(encoding="utf-8"))
FIXTURES = ROOT / "fixtures/demo"


def validate(name: str, value: dict) -> None:
    schema = SPEC["components"]["schemas"][name]
    validator = Draft202012Validator(schema, resolver=RefResolver.from_schema(SPEC))
    errors = sorted(validator.iter_errors(value), key=lambda item: list(item.path))
    assert not errors, "\n".join(error.message for error in errors[:10])


def test_batch_and_submission_fixtures_match_contract() -> None:
    batches = json.loads((FIXTURES / "batches.json").read_text(encoding="utf-8"))
    submissions = json.loads((FIXTURES / "submissions/index.json").read_text(encoding="utf-8"))
    for item in batches:
        validate("BatchSummary", item)
    for item in submissions:
        validate("SubmissionRow", item)


def test_all_counts_derive_from_rows() -> None:
    batches = {
        item["id"]: item
        for item in json.loads((FIXTURES / "batches.json").read_text(encoding="utf-8"))
    }
    submissions = json.loads((FIXTURES / "submissions/index.json").read_text(encoding="utf-8"))
    for batch_id, batch in batches.items():
        rows = [item for item in submissions if item["batch_id"] == batch_id]
        statuses = Counter(item["status"] for item in rows)
        ready = statuses["ai_done"] + statuses["in_review"]
        needs_manual = statuses["needs_ocr"]
        processing = sum(
            statuses[value]
            for value in ("uploaded", "extracting", "ocr_running", "queued", "marking")
        )
        assert len(rows) == batch["counts"]["total"]
        assert ready == batch["counts"]["ready"]
        assert needs_manual == batch["counts"]["needs_manual"]
        assert processing == batch["counts"]["processing"]
        assert statuses["confirmed"] == batch["counts"]["confirmed"]
        assert (
            sum(
                item["confidence"] == "low" and item["status"] in {"ai_done", "in_review"}
                for item in rows
            )
            == batch["counts"]["low_confidence"]
        )


def test_evidence_offsets_are_verbatim() -> None:
    review = json.loads((FIXTURES / "reviews/sub_asgn2_000001.json").read_text(encoding="utf-8"))
    text = "\n\n".join(item["text"] for item in review["document"]["paragraphs"])
    for evidence in review["evidence"]:
        assert text[evidence["start_offset"] : evidence["end_offset"]] == evidence["quote"]


def test_lightweight_rows_are_explicitly_mocked() -> None:
    rows = json.loads((FIXTURES / "submissions/index.json").read_text(encoding="utf-8"))
    for batch_id in ("bat_asgn2", "bat_asgn1"):
        batch_rows = [item for item in rows if item["batch_id"] == batch_id]
        full_rows = [item for item in batch_rows if not item["_mock"]]
        ready_rows = [item for item in batch_rows if item["status"] in {"ai_done", "in_review"}]
        assert len(full_rows) == 6
        assert ready_rows[:6] == full_rows
        assert all((FIXTURES / "reviews" / f"{item['id']}.json").exists() for item in full_rows)
