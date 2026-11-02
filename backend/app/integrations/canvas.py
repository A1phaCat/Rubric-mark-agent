"""Canvas LMS: read courses, assignments, rubrics and submissions; write grades back.

Two interchangeable sources share one interface:

* ``CanvasAPI`` talks to a Canvas instance's REST API with a personal access token
  (``Authorization: Bearer``), following ``Link: rel="next"`` pagination.
* ``OfflineCanvas`` reads a Canvas export folder for development and demos without
  credentials: ``*.json`` files shaped like the Canvas API (``{"course", "assignment",
  "rubric"}``, the same format the rubric parser imports) and the students' files under
  ``submissions/<assignment_id>/<user_id>_<file name>``. Grade write-backs are appended to
  ``grade-pushes.jsonl`` in that folder instead of being sent anywhere.

Grade payloads are built by :func:`grade_update`, which is pure, so a dry run shows the
exact request a live push would send.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import httpx


class CanvasError(RuntimeError):
    """Canvas refused a request or the export folder is unusable."""


class CanvasSource(Protocol):
    mode: str

    def courses(self) -> list[dict[str, Any]]: ...

    def assignments(self, course_id: str) -> list[dict[str, Any]]: ...

    def assignment(self, course_id: str, assignment_id: str) -> dict[str, Any]: ...

    def course(self, course_id: str) -> dict[str, Any]: ...

    def submissions(self, course_id: str, assignment_id: str) -> list[dict[str, Any]]: ...

    def download(self, attachment: dict[str, Any]) -> bytes: ...

    def put_grade(self, course_id: str, assignment_id: str, user_id: str, body: dict[str, Any]) -> dict[str, Any]: ...


def _next_link(header: str | None) -> str | None:
    for part in (header or "").split(","):
        match = re.search(r'<([^>]+)>;\s*rel="next"', part)
        if match:
            return match.group(1)
    return None


@dataclass
class CanvasAPI:
    base_url: str
    token: str
    timeout: float = 30.0
    transport: httpx.BaseTransport | None = None
    mode: str = "api"

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {self.token}", "Accept": "application/json"},
            timeout=self.timeout,
            transport=self.transport,
            follow_redirects=True,
        )

    def _get_all(self, path: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        with self._client() as client:
            url: str | None = path
            query: dict[str, Any] | None = {"per_page": 100, **(params or {})}
            while url:
                response = client.get(url, params=query)
                self._check(response)
                items.extend(response.json())
                url, query = _next_link(response.headers.get("link")), None
        return items

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._client() as client:
            response = client.get(path, params=params)
            self._check(response)
            return response.json()

    @staticmethod
    def _check(response: httpx.Response) -> None:
        if response.status_code >= 400:
            raise CanvasError(f"Canvas returned HTTP {response.status_code} for {response.request.url.path}")

    def courses(self) -> list[dict[str, Any]]:
        return self._get_all("/api/v1/courses", {"enrollment_type": "teacher"}) + self._get_all(
            "/api/v1/courses", {"enrollment_type": "ta"})

    def course(self, course_id: str) -> dict[str, Any]:
        return self._get(f"/api/v1/courses/{course_id}")

    def assignments(self, course_id: str) -> list[dict[str, Any]]:
        return self._get_all(f"/api/v1/courses/{course_id}/assignments")

    def assignment(self, course_id: str, assignment_id: str) -> dict[str, Any]:
        return self._get(f"/api/v1/courses/{course_id}/assignments/{assignment_id}")

    def submissions(self, course_id: str, assignment_id: str) -> list[dict[str, Any]]:
        return self._get_all(f"/api/v1/courses/{course_id}/assignments/{assignment_id}/submissions",
                             {"include[]": "user"})

    def download(self, attachment: dict[str, Any]) -> bytes:
        with self._client() as client:
            response = client.get(str(attachment["url"]))
            self._check(response)
            return response.content

    def put_grade(self, course_id: str, assignment_id: str, user_id: str, body: dict[str, Any]) -> dict[str, Any]:
        with self._client() as client:
            response = client.put(
                f"/api/v1/courses/{course_id}/assignments/{assignment_id}/submissions/{user_id}", json=body)
            self._check(response)
            return response.json()


class OfflineCanvas:
    """A Canvas export folder that behaves like the API (no network, no credentials)."""

    mode = "offline"

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        if not self.root.is_dir():
            raise CanvasError(f"Canvas export folder {self.root} does not exist")
        self._exports: list[dict[str, Any]] = []
        for path in sorted(self.root.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("course"), dict) and isinstance(data.get("assignment"), dict):
                assignment = dict(data["assignment"])
                if isinstance(data.get("rubric"), list):
                    assignment.setdefault("rubric", data["rubric"])
                self._exports.append({"course": data["course"], "assignment": assignment})

    def courses(self) -> list[dict[str, Any]]:
        seen: dict[str, dict[str, Any]] = {}
        for item in self._exports:
            seen.setdefault(str(item["course"]["id"]), item["course"])
        return list(seen.values())

    def course(self, course_id: str) -> dict[str, Any]:
        for course in self.courses():
            if str(course["id"]) == str(course_id):
                return course
        raise CanvasError(f"Course {course_id} is not in the export")

    def assignments(self, course_id: str) -> list[dict[str, Any]]:
        return [item["assignment"] for item in self._exports if str(item["course"]["id"]) == str(course_id)]

    def assignment(self, course_id: str, assignment_id: str) -> dict[str, Any]:
        for assignment in self.assignments(course_id):
            if str(assignment["id"]) == str(assignment_id):
                return assignment
        raise CanvasError(f"Assignment {assignment_id} is not in course {course_id}")

    def submissions(self, course_id: str, assignment_id: str) -> list[dict[str, Any]]:
        self.assignment(course_id, assignment_id)
        folder = self.root / "submissions" / str(assignment_id)
        rows: list[dict[str, Any]] = []
        for path in sorted(folder.glob("*")) if folder.is_dir() else []:
            user_id, _, name = path.name.partition("_")
            if not path.is_file() or not user_id.isdigit() or not name:
                continue
            rows.append({
                "id": int(user_id) * 10 + 1, "user_id": int(user_id), "assignment_id": assignment_id,
                "workflow_state": "submitted", "submitted_at": None,
                "user": {"id": int(user_id), "sis_user_id": None},
                "attachments": [{"id": int(user_id), "display_name": name, "filename": name,
                                 "url": str(path), "size": path.stat().st_size}],
            })
        return rows

    def download(self, attachment: dict[str, Any]) -> bytes:
        path = Path(str(attachment["url"])).resolve()
        if self.root.resolve() not in path.parents:
            raise CanvasError("Attachment is outside the export folder")
        return path.read_bytes()

    def put_grade(self, course_id: str, assignment_id: str, user_id: str, body: dict[str, Any]) -> dict[str, Any]:
        record = {"at": datetime.now(timezone.utc).isoformat(), "course_id": course_id,
                  "assignment_id": assignment_id, "user_id": user_id, "body": body}
        with (self.root / "grade-pushes.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")
        return {"user_id": user_id, "grade": body["submission"]["posted_grade"], "workflow_state": "graded"}


def rubric_export(course: dict[str, Any], assignment: dict[str, Any]) -> dict[str, Any]:
    """The ``{"course", "assignment", "rubric"}`` document the rubric parser imports."""

    rubric = assignment.get("rubric")
    if not isinstance(rubric, list) or not rubric:
        raise CanvasError("This assignment has no Canvas rubric")
    return {"course": course, "assignment": {k: v for k, v in assignment.items() if k != "rubric"}, "rubric": rubric}


def _norm(text: str) -> str:
    text = html.unescape(html.unescape(str(text or "")))
    text = re.sub(r"<[^>]+>", " ", str(text or "")).replace("\u00a0", " ")
    return re.sub(r"\s+", " ", text).strip().lower()


def grade_update(
    canvas_rubric: list[dict[str, Any]] | None,
    criteria: list[dict[str, Any]],
    total: float,
    comment: str | None = None,
) -> dict[str, Any]:
    """Canvas grade-update body: total, optional comment, per-criterion rubric points.

    ``criteria`` are the marker's ``{"name", "score", "comment"}``; each is matched to the
    Canvas criterion with the same description (the rubric was imported from it).
    """

    body: dict[str, Any] = {"submission": {"posted_grade": round(float(total), 2)}}
    if comment:
        body["comment"] = {"text_comment": comment}
    by_name = {_norm(item.get("description", "")): item for item in canvas_rubric or []}
    assessment: dict[str, Any] = {}
    for criterion in criteria:
        match = by_name.get(_norm(criterion["name"]))
        if match is None:
            continue
        entry: dict[str, Any] = {"points": round(float(criterion["score"]), 2)}
        if criterion.get("comment"):
            entry["comments"] = criterion["comment"]
        assessment[str(match["id"])] = entry
    if assessment:
        body["rubric_assessment"] = assessment
    return body
