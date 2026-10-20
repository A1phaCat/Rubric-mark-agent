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
    assert len([item for item in rubrics if item["is_sample"]]) == 6


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


def test_new_batches_are_pinned_above_samples_and_reseeding_keeps_them(client: TestClient) -> None:
    created = client.post(
        "/api/v1/batches",
        json={"name": "Demo batch", "unit": None, "term_id": "term_2026s2", "rubric_id": "rub_shortanswer", "rubric_version": 1},
    ).json()["batch"]
    assert created["pinned"] is True
    assert client.get("/api/v1/batches").json()["items"][0]["id"] == created["id"]
    assert client.put(f"/api/v1/batches/{created['id']}/pin", json={"pinned": False}).json()["pinned"] is False
    items = client.get("/api/v1/batches").json()["items"]
    assert items[-1]["id"] == created["id"]
    seed()  # re-seeding replaces the samples but keeps the tutor's batch and its rubric
    with SessionLocal() as session:
        assert session.get(Batch, created["id"]) is not None
        assert len(list(session.scalars(select(Batch).where(Batch.is_sample.is_(True))))) == 3
