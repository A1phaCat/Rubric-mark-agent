"""Canvas: API client paging/auth, offline export source, import into a batch, grade write-back."""

from __future__ import annotations

import json
import shutil

import httpx
import pytest
from fastapi.testclient import TestClient

from app.integrations.canvas import CanvasAPI, CanvasError, grade_update
from app.main import app
from app.sample.seed import FILES, RUBRIC_FILES

COURSE, ASSIGNMENT = "73762", "693964"


def test_api_client_sends_the_token_and_follows_pagination() -> None:
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, request.url.params.get("page"),
                     request.headers.get("authorization")))
        if request.method == "PUT":
            return httpx.Response(200, json={"grade": json.loads(request.content)["submission"]["posted_grade"]})
        if request.url.params.get("page") == "2":
            return httpx.Response(200, json=[{"id": 2}])
        return httpx.Response(200, json=[{"id": 1}], headers={
            "link": '<https://canvas.test/api/v1/courses/1/assignments?page=2&per_page=100>; rel="next"'})

    api = CanvasAPI("https://canvas.test", "t0ken", transport=httpx.MockTransport(handler))
    assert [a["id"] for a in api.assignments("1")] == [1, 2]
    assert api.put_grade("1", "9", "42", {"submission": {"posted_grade": 7.5}}) == {"grade": 7.5}
    assert all(auth == "Bearer t0ken" for *_, auth in seen)
    assert seen[-1][:2] == ("PUT", "/api/v1/courses/1/assignments/9/submissions/42")


def test_api_errors_do_not_echo_the_token() -> None:
    api = CanvasAPI("https://canvas.test", "s3cret",
                    transport=httpx.MockTransport(lambda _r: httpx.Response(401, json={"errors": []})))
    with pytest.raises(CanvasError) as error:
        api.courses()
    assert "401" in str(error.value) and "s3cret" not in str(error.value)


def test_grade_update_maps_criteria_to_canvas_rubric_ids() -> None:
    rubric = [{"id": "_1", "description": "Clarity&nbsp;<b>of</b> writing"}, {"id": "_2", "description": "Design"}]
    body = grade_update(rubric, [{"name": "Clarity of writing", "score": 3.456, "comment": "clear"},
                                 {"name": "Unknown", "score": 1}], 9.5, "Well done")
    assert body == {"submission": {"posted_grade": 9.5}, "comment": {"text_comment": "Well done"},
                    "rubric_assessment": {"_1": {"points": 3.46, "comments": "clear"}}}


@pytest.fixture()
def export(tmp_path):
    shutil.copy(RUBRIC_FILES / "comp5348-asgn1.json", tmp_path / "comp5348-asgn1.json")
    folder = tmp_path / "submissions" / ASSIGNMENT
    folder.mkdir(parents=True)
    for user_id, path in zip((5001, 5002), sorted(FILES.glob("*_ASGN1.docx"))[:2]):
        shutil.copy(path, folder / f"{user_id}_{path.name}")
    return tmp_path


def _drain() -> None:
    from app.jobs import worker

    while worker.run_once("test-canvas"):
        pass


def test_offline_canvas_import_and_dry_run_write_back(export) -> None:
    from app.sample.seed import seed

    seed()  # the local user and a term the batch can belong to
    with TestClient(app) as client:
        try:
            assert client.get("/api/v1/canvas/courses").status_code in {200, 409}
            saved = client.put("/api/v1/settings/canvas", json={"offline_dir": str(export)}).json()
            assert saved["enabled"] is True and saved["mode"] == "offline" and saved["has_token"] is False

            courses = client.get("/api/v1/canvas/courses").json()
            assert COURSE in {c["id"] for c in courses["items"]}
            assignments = client.get(f"/api/v1/canvas/courses/{COURSE}/assignments").json()["items"]
            assert assignments[0]["id"] == ASSIGNMENT and assignments[0]["has_rubric"] is True

            imported = client.post(f"/api/v1/canvas/courses/{COURSE}/assignments/{ASSIGNMENT}/import")
            assert imported.status_code == 201, imported.text
            result = imported.json()
            assert result["imported"] == 2 and result["mode"] == "offline"
            batch_id = result["batch_id"]
            rows = client.get(f"/api/v1/batches/{batch_id}/submissions").json()
            sids = sorted(item["sid"] for item in rows["items"])
            assert sids == ["canvas-5001", "canvas-5002"]

            # nothing confirmed yet: the default dry run sends nothing
            dry = client.post(f"/api/v1/canvas/batches/{batch_id}/push-grades").json()
            assert dry["dry_run"] is True and dry["would_send"] == 0 and len(dry["skipped"]) == 2

            batch = client.get(f"/api/v1/batches/{batch_id}").json()["batch"]
            started = client.post(f"/api/v1/batches/{batch_id}/start",
                                  json={"provider": "fake", "model": "fake-marker-v1", "version": batch["version"]})
            assert started.status_code in {200, 202}, started.text
            _drain()

            preview = client.post(f"/api/v1/canvas/batches/{batch_id}/push-grades",
                                  json={"include_unconfirmed": True}).json()
            assert preview["dry_run"] is True and preview["would_send"] == 2 and preview["sent"] == 0
            first = preview["requests"][0]
            assert first["path"].endswith(f"/assignments/{ASSIGNMENT}/submissions/{first['user_id']}")
            assert first["body"]["rubric_assessment"] and all(k.startswith("_") for k in first["body"]["rubric_assessment"])
            assert not (export / "grade-pushes.jsonl").exists()

            live = client.post(f"/api/v1/canvas/batches/{batch_id}/push-grades",
                               json={"include_unconfirmed": True, "dry_run": False}).json()
            assert live["sent"] == 2
            pushed = (export / "grade-pushes.jsonl").read_text(encoding="utf-8").splitlines()
            assert len(pushed) == 2
        finally:
            client.put("/api/v1/settings/canvas", json={"offline_dir": ""})


def test_live_push_is_refused_when_canvas_would_release_grades(monkeypatch) -> None:
    from app.services import canvas_service

    class AutoPosting:
        mode = "api"

        def assignment(self, *_):
            return {"id": 1, "post_manually": False, "rubric": []}

    class Row:
        value_encrypted = json.dumps({"course_id": "1", "assignment_id": "1", "users": {}})

    class Db:
        def get(self, model, key):
            return Row() if str(key).startswith("canvas.link.") else object()

    with pytest.raises(CanvasError, match="manual posting"):
        canvas_service.push_grades(Db(), None, AutoPosting(), "bat_x", dry_run=False)
    assert canvas_service.push_grades(Db(), None, AutoPosting(), "bat_x")["dry_run"] is True
