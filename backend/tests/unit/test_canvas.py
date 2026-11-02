"""Read-only Canvas connection: settings, courses, rubric import and submission import."""

import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.canvas import CanvasClient, CanvasError, normalise_base_url
from app.config import Settings
from app.db.models.batch import Batch
from app.db.models.submission import Submission
from app.main import app
from app.rubric.parser import parse_rubric_text
from app.services import canvas_service
from tests.unit.test_full_text_grading import stored  # noqa: F401

RUBRIC = [
    {"id": "_1", "description": "Problem and motivation", "long_description": "Why it matters", "points": 1.5,
     "ratings": [{"description": "Excellent", "long_description": "Specific and compelling", "points": 1.5},
                 {"description": "Weak", "long_description": "Vague", "points": 0}]},
    {"id": "_2", "description": "Design", "long_description": "", "points": 2,
     "ratings": [{"description": "Excellent", "long_description": "Credible", "points": 2},
                 {"description": "Weak", "long_description": "Vague", "points": 0}]},
]
ASSIGNMENT = {"id": 7, "name": "Group Business Proposal", "due_at": "2026-09-01T13:59:00Z", "points_possible": 10,
              "rubric": RUBRIC, "rubric_settings": {"title": "Proposal rubric", "points_possible": 3.5},
              "submission_types": ["online_upload"], "has_submitted_submissions": True, "group_category_id": 3}
PDF = b"%PDF-1.4\n%fake\n"


def canvas_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if request.headers.get("authorization") != "Bearer good-token" and "files" not in path:
        return httpx.Response(401, json={"errors": [{"message": "Invalid access token."}]})
    if path == "/api/v1/users/self":
        return httpx.Response(200, json={"id": 1, "name": "Darin"})
    if path == "/api/v1/courses" and request.url.params.get("page") != "2":
        return httpx.Response(200, json=[{"id": 11, "name": "ELEC5623", "course_code": "ELEC5623"}],
                              headers={"link": f'<{request.url.copy_merge_params({"page": "2"})}>; rel="next"'})
    if path == "/api/v1/courses":
        return httpx.Response(200, json=[{"id": 12, "name": "COMP5348", "course_code": "COMP5348"}])
    if path == "/api/v1/courses/11":
        return httpx.Response(200, json={"id": 11, "name": "ELEC5623 Applied GenAI", "course_code": "ELEC5623"})
    if path == "/api/v1/courses/11/assignments":
        return httpx.Response(200, json=[ASSIGNMENT, {"id": 8, "name": "Quiz", "rubric": None}])
    if path == "/api/v1/courses/11/assignments/7":
        return httpx.Response(200, json=ASSIGNMENT)
    if path == "/api/v1/courses/11/assignments/7/submissions" and request.headers.get("x-role") == "student":
        return httpx.Response(403, json={"status": "unauthorized"})
    if path == "/api/v1/courses/11/assignments/7/submissions/self":
        return httpx.Response(200, json={"id": 102, "user_id": 9, "user": {"name": "Darin"},
                                         "attachments": [{"filename": "group14.pdf", "url": "https://files.canvas.test/files/2"}]})
    if path == "/api/v1/courses/11/assignments/7/submissions":
        return httpx.Response(200, json=[
            {"id": 100, "user_id": 5, "user": {"name": "Ana Li", "sortable_name": "Li, Ana", "sis_user_id": "530123456"},
             "attachments": [{"filename": "proposal.pdf", "url": "https://files.canvas.test/files/1", "content-type": "application/pdf"}]},
            {"id": 101, "user_id": 6, "user": {"name": "Ben Ho"}, "attachments": [], "body": None},
        ])
    if request.url.host == "files.canvas.test":
        return httpx.Response(200, content=PDF)
    return httpx.Response(404)


def _client(token: str = "good-token") -> CanvasClient:
    return CanvasClient("canvas.test", token, transport=httpx.MockTransport(canvas_handler))


def test_addresses_are_normalised() -> None:
    assert normalise_base_url("canvas.sydney.edu.au/") == "https://canvas.sydney.edu.au"
    assert normalise_base_url("https://canvas.test/api/v1") == "https://canvas.test"
    with pytest.raises(CanvasError):
        normalise_base_url(" ")


def test_pages_are_followed_and_a_bad_token_is_explained() -> None:
    names = [course["name"] for course in asyncio.run(_client().courses())]
    assert names == ["ELEC5623", "COMP5348"]
    with pytest.raises(CanvasError, match="rejected the access token"):
        asyncio.run(_client("expired").me())


def test_the_assignment_rubric_parses_like_a_canvas_export(monkeypatch) -> None:
    monkeypatch.setattr(canvas_service, "client", lambda *_a, **_k: _client())
    text, name = asyncio.run(canvas_service.rubric_export(None, "11", "7"))
    parsed = parse_rubric_text(text, name)
    assert parsed["_parser"] == "canvas_json"
    assert [c["name"] for c in parsed["criteria"]] == ["Problem and motivation", "Design"]
    assert "Canvas" in parsed["source"] and "Group Business Proposal" in parsed["source"]


def test_assignments_report_whether_a_rubric_is_attached(monkeypatch) -> None:
    monkeypatch.setattr(canvas_service, "client", lambda *_a, **_k: _client())
    items = asyncio.run(canvas_service.assignments(None, "11"))
    assert [(a["name"], a["has_rubric"], a["criteria"]) for a in items] == [
        ("Group Business Proposal", True, 2), ("Quiz", False, 0)]


def test_submissions_are_downloaded_into_the_batch_with_their_sid(stored, monkeypatch, tmp_path) -> None:  # noqa: F811
    monkeypatch.setattr(canvas_service, "client", lambda *_a, **_k: _client())
    settings = Settings(data_dir=tmp_path)
    for path in settings.runtime_paths().values():
        path.mkdir(parents=True, exist_ok=True)
    with stored() as session:
        result = asyncio.run(canvas_service.import_submissions(session, settings, session.get(Batch, "bat_t"), "11", "7"))
        assert result["summary"]["canvas_submissions"] == 2 and result["summary"]["with_files"] == 1
        assert result["summary"]["scope"] == "class"
        assert result["summary"]["accepted"] == 1 and result["summary"]["needs_sid"] == 0
        sids = {row.sid for row in session.query(Submission).filter(Submission.batch_id == "bat_t")}
        assert "SID-530123456" in sids


def test_settings_save_the_token_server_side_and_test_against_canvas(monkeypatch) -> None:
    accounts = []
    monkeypatch.setattr(canvas_service, "protect_secret", lambda value, account: accounts.append(account) or f"x:{value}")
    monkeypatch.setattr(canvas_service, "client", lambda _db, base_url=None, token=None: _client(token or "good-token"))
    with TestClient(app) as http:
        saved = http.put("/api/v1/settings/canvas", json={"base_url": "canvas.test", "token": "good-token"}).json()
        assert saved["has_token"] is True and saved["base_url"] == "https://canvas.test"
        assert "good-token" not in json.dumps(saved)
        assert accounts == [canvas_service.KEYCHAIN_ACCOUNT]  # never the AI key's Keychain entry
        assert http.post("/api/v1/settings/canvas/test", json={}).json()["user"] == "Darin"
        assert http.get("/api/v1/settings/canvas").json()["user"] == "Darin"
        bad = http.post("/api/v1/settings/canvas/test", json={"token": "expired"}).json()
        assert bad["ok"] is False and "rejected" in bad["message"]
        assert [c["code"] for c in http.get("/api/v1/canvas/courses").json()["items"]] == ["ELEC5623", "COMP5348"]
        http.put("/api/v1/settings/canvas", json={"clear_token": True})


def test_a_student_token_falls_back_to_its_own_submission() -> None:
    student = CanvasClient("canvas.test", "good-token", transport=httpx.MockTransport(canvas_handler))
    student._headers["x-role"] = "student"
    found, scope = asyncio.run(student.submissions("11", "7"))
    assert scope == "own" and [item["id"] for item in found] == [102]
    found, scope = asyncio.run(_client().submissions("11", "7"))
    assert scope == "class" and len(found) == 2
