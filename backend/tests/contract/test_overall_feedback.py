"""Overall feedback on the report: an AI draft from the confirmed marks that a tutor approves."""

import pytest
from fastapi.testclient import TestClient

from app.llm.fake import FakeLLM
from app.main import app
from app.report import feedback as overall
from app.report import project_for_audience
from app.sample.seed import seed
from app.services import feedback_service


@pytest.fixture(scope="module")
def client() -> TestClient:
    seed()
    return TestClient(app)


def _confirmed(client: TestClient, batch_id: str) -> str:
    items = client.get(f"/api/v1/batches/{batch_id}/submissions").json()["items"]
    return next(item["id"] for item in items if item["status"] == "confirmed")


def test_a_draft_is_written_for_the_tutor_and_hidden_from_the_student(client, monkeypatch) -> None:
    monkeypatch.setattr(feedback_service, "build_llm", lambda _settings: FakeLLM())
    submission = _confirmed(client, "bat_sample_asgn1")
    report = client.post(f"/api/v1/submissions/{submission}/feedback/draft").json()
    assert report["feedback"]["status"] == "draft" and report["feedback"]["summary"]
    assert report["feedback"]["stale"] is False
    student = client.get(f"/api/v1/submissions/{submission}/report?audience=student").json()
    assert student["feedback"] is None

    approved = client.put(f"/api/v1/submissions/{submission}/feedback", json={
        "summary": "Edited by the tutor.", "strengths": "First strength\n- Second strength",
        "improvements": ["One improvement"], "next_steps": [], "approve": True}).json()
    assert approved["feedback"]["status"] == "approved"
    assert approved["feedback"]["strengths"] == ["First strength", "Second strength"]
    student = client.get(f"/api/v1/submissions/{submission}/report?audience=student").json()
    assert student["feedback"]["summary"] == "Edited by the tutor."
    assert "basis" not in student["feedback"] and "model" not in student["feedback"]


def test_a_finalised_batch_keeps_its_feedback_locked(client) -> None:
    submission = _confirmed(client, "bat_sample_quiz3")
    response = client.post(f"/api/v1/submissions/{submission}/feedback/draft")
    assert response.status_code == 409
    assert client.put(f"/api/v1/submissions/{submission}/feedback", json={"summary": "x"}).status_code == 409


def test_feedback_goes_stale_when_the_marks_it_was_written_from_change() -> None:
    criteria = [{"criterion_id": "c1", "score": 1.0, "comment": "Good"}, {"criterion_id": "c2", "score": 2, "comment": ""}]
    written = overall.basis(criteria)
    assert overall.basis(list(reversed(criteria))) == written
    assert overall.basis([{**criteria[0], "score": 1.5}, criteria[1]]) != written
    assert overall.basis([{**criteria[0], "comment": "Very good"}, criteria[1]]) != written


def test_model_output_is_trimmed_to_the_four_fields() -> None:
    cleaned = overall.clean({"summary": "  A  summary. ", "strengths": ["a", "", "b", "c", "d"], "grade": "HD",
                             "next_steps": "not a list"})
    assert cleaned == {"summary": "A summary.", "strengths": ["a", "b", "c"], "improvements": [], "next_steps": []}


def test_the_prompt_carries_the_confirmed_marks_but_not_the_numbers() -> None:
    report = {"batch": {"name": "Proposal"}, "criteria": [
        {"name": "Design", "band": "1.5 points", "descriptor": "Sound", "band_rank": 1, "band_count": 5,
         "comment": "Explain the retrieval step", "internal_rationale": "Mostly sound", "score": 1.5,
         "evidence": [{"page": 3, "paragraph": "¶2"}]}]}
    text = overall.prompt(report)
    assert "Explain the retrieval step" in text and "p.3 ¶2" in text and "Do not mention marks" in text
    projected = project_for_audience({"feedback": {"status": "draft", "summary": "x"}, "criteria": []}, "student")
    assert projected["feedback"] is None
