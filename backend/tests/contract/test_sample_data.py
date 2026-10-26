"""The sample batches are real database rows rendered by the same API as user data."""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models.batch import Batch
from app.db.models.submission import AIResult, Evidence, Submission
from app.db.session import SessionLocal
from app.main import app
from app.sample.seed import seed


@pytest.fixture(scope="module")
def client() -> TestClient:
    seed()
    return TestClient(app)


def test_three_pinned_sample_batches_in_distinct_states(client: TestClient) -> None:
    items = client.get("/api/v1/batches").json()["items"]
    samples = {item["id"]: item for item in items if item["is_sample"]}
    assert {item["status"] for item in samples.values()} == {"in_review", "completed", "finalised"}
    assert all(item["pinned"] for item in samples.values())
    rubrics = client.get("/api/v1/rubrics").json()["items"]
    assert len([item for item in rubrics if item["is_sample"]]) == 14


def test_every_evidence_quote_is_in_the_extracted_text() -> None:
    with SessionLocal() as session:
        rows = session.execute(
            select(Evidence, Submission)
            .join(AIResult, AIResult.id == Evidence.ai_result_id)
            .join(Submission, Submission.id == AIResult.submission_id)
        ).all()
        assert rows
        for evidence, submission in rows:
            document = json.loads(submission.document_json)
            block = next(
                b for b in document["paragraphs"] if b["page"] == evidence.page and b.get("label") == evidence.para
            )
            assert evidence.quote in block["text"]


def test_home_summary_queue_results_and_report_come_from_rows(client: TestClient) -> None:
    summary = client.get("/api/v1/me/summary").json()
    assert summary["ready_for_review"]["count"] == 3
    assert summary["needs_manual"]["count"] == 1
    queue = client.get("/api/v1/me/queue?limit=10").json()["items"]
    assert [item["reason"] for item in queue][-1] == "needs_manual"
    assert queue[0]["reason"] == "low_confidence"

    results = client.get("/api/v1/batches/bat_sample_quiz3/results").json()
    assert results["locked"] is True
    assert sum(item["count"] for item in results["distribution"]) == 5
    confirmed = results["submissions"]["items"][0]
    internal = client.get(f"/api/v1/submissions/{confirmed['id']}/report").json()
    student = client.get(f"/api/v1/submissions/{confirmed['id']}/report?audience=student").json()
    assert internal["feedback"]["summary"] and internal["ai_total"] is not None
    assert "ai_total" not in student and all("ai_score" not in c for c in student["criteria"])

    csv = client.get("/api/v1/batches/bat_sample_asgn1/export.csv").text.splitlines()
    assert csv[0].startswith("sid,status,ai_total,final_total") and len(csv) == 5


def test_manual_marking_submission_opens_with_empty_criteria(client: TestClient) -> None:
    rows = client.get("/api/v1/batches/bat_sample_asgn2/submissions?filter=needs_manual").json()["items"]
    review = client.get(f"/api/v1/submissions/{rows[0]['id']}/review").json()
    assert review["submission"]["needs_manual"] is True
    assert review["evidence"] == []
    assert all(item["ai_score"] is None and item["score"] is None for item in review["rubric"]["criteria"])


def test_at_most_three_batches_are_pinned_and_new_ones_go_on_top(client: TestClient) -> None:
    body = {"name": "Demo batch", "unit": None, "term_id": "term_2026s2", "rubric_id": "rub_shortanswer", "rubric_version": 1}
    created = client.post("/api/v1/batches", json=body).json()
    batch = created["batch"]
    assert batch["pinned"] is True
    assert [item["name"] for item in created["unpinned"]] == ["Quiz 3 — Short Answer"]  # oldest pin
    items = client.get("/api/v1/batches").json()["items"]
    assert items[0]["id"] == batch["id"]
    assert sum(item["pinned"] for item in items) == 3

    # Re-pinning a sample evicts the oldest remaining pin; unpinning drops below the pins.
    repin = client.put("/api/v1/batches/bat_sample_quiz3/pin", json={"pinned": True}).json()
    assert len(repin["unpinned"]) == 1
    assert client.put(f"/api/v1/batches/{batch['id']}/pin", json={"pinned": False}).json()["pinned"] is False
    items = client.get("/api/v1/batches").json()["items"]
    assert sum(item["pinned"] for item in items) <= 3
    assert not next(item for item in items if item["id"] == batch["id"])["pinned"]


def test_reset_restores_samples_and_keeps_the_tutors_batches(client: TestClient) -> None:
    # Mark a sample submission, then reset: the sample goes back to its starting state.
    rows = client.get("/api/v1/batches/bat_sample_asgn2/submissions?filter=ready").json()["items"]
    review = client.get(f"/api/v1/submissions/{rows[0]['id']}/review").json()
    version = review["submission"]["version"]
    assert client.post(f"/api/v1/submissions/{rows[0]['id']}/confirm", json={"version": version}).status_code == 200
    before = client.get("/api/v1/batches/bat_sample_asgn2").json()["batch"]["counts"]["confirmed"]
    mine = client.post(
        "/api/v1/batches",
        json={"name": "Mine", "unit": None, "term_id": "term_2026s2", "rubric_id": "rub_shortanswer", "rubric_version": 1},
    ).json()["batch"]

    result = client.post("/api/v1/samples/reset").json()
    assert result["reset"] is True and result["batches"] == 3
    after = client.get("/api/v1/batches/bat_sample_asgn2").json()["batch"]["counts"]["confirmed"]
    assert before == 2 and after == 1
    items = client.get("/api/v1/batches").json()["items"]
    assert [item["id"] for item in items[:3]] == ["bat_sample_asgn2", "bat_sample_asgn1", "bat_sample_quiz3"]
    with SessionLocal() as session:
        assert session.get(Batch, mine["id"]) is not None  # the tutor's batch is kept (unpinned)
        assert len(list(session.scalars(select(Batch).where(Batch.is_sample.is_(True))))) == 3


def test_new_batch_defaults_to_the_current_term(client: TestClient) -> None:
    term = client.get("/api/v1/me").json()["term"]
    created = client.post(
        "/api/v1/batches", json={"name": "No term given", "rubric_id": "rub_shortanswer", "rubric_version": 1}
    ).json()["batch"]
    assert created["term"]["id"] == term["id"]


def test_local_account_name_is_stored_and_editable(client: TestClient) -> None:
    original = client.get("/api/v1/me").json()["user"]["name"]
    assert original
    assert client.put("/api/v1/me", json={"name": "  "}).status_code == 422
    renamed = client.put("/api/v1/me", json={"name": "Dr Lee"}).json()
    assert renamed["user"]["name"] == "Dr Lee"
    assert client.get("/api/v1/me").json()["user"]["name"] == "Dr Lee"
    client.put("/api/v1/me", json={"name": original})


def test_canvas_export_uploads_and_keeps_criterion_descriptions(client: TestClient) -> None:
    from app.sample.seed import RUBRIC_FILES

    content = (RUBRIC_FILES / "elec5623-final-report.json").read_bytes()
    parsed = client.post(
        "/api/v1/rubrics/parse-file", files={"file": ("ELEC5623.json", content, "application/json")}
    ).json()
    assert parsed["parser"] == "canvas_json"
    assert {w["severity"] for w in parsed["warnings"]} == {"info"}
    rubric = parsed["rubric"]
    saved = client.post("/api/v1/rubrics", json={"title": rubric["title"], "source": "test", "criteria": rubric["criteria"]})
    assert saved.status_code == 201
    stored = client.get(f"/api/v1/rubrics/{saved.json()['rubric']['id']}").json()["rubric"]["criteria"][0]
    assert stored["description"].startswith("A functional and coherent MVP")
    assert [level["label"] for level in stored["levels"]] == ["Exceeds", "Mastery", "Near", "Below", "No Evidence"]
    assert all(level["description"] == "" for level in stored["levels"])
