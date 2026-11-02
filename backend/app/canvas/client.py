"""A small client for the Canvas REST API (read-only, personal access token)."""

from __future__ import annotations

import re
from typing import Any

import httpx

_NEXT = re.compile(r'<([^>]+)>;\s*rel="next"')
_MAX_PAGES = 50
_MAX_ATTACHMENT_BYTES = 50 * 1024 * 1024


class CanvasError(Exception):
    """Canvas refused or could not be reached; the message is safe to show a tutor."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def normalise_base_url(value: str) -> str:
    """``canvas.sydney.edu.au`` or ``https://canvas.sydney.edu.au/`` → ``https://canvas.sydney.edu.au``."""

    text = (value or "").strip().rstrip("/")
    if not text:
        raise CanvasError("Enter the Canvas address, for example canvas.sydney.edu.au")
    if not re.match(r"^https?://", text):
        text = "https://" + text
    return re.sub(r"/api/v1$", "", text)


class CanvasClient:
    def __init__(self, base_url: str, token: str, *, timeout: float = 30.0,
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        if not token:
            raise CanvasError("Add a Canvas access token first (Account → Settings → New access token)")
        self.base_url = normalise_base_url(base_url)
        self._headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        self._timeout = timeout
        self._transport = transport  # tests only

    def _client(self) -> httpx.AsyncClient:
        # Authorization is dropped on redirects to another host (file downloads go to storage).
        return httpx.AsyncClient(headers=self._headers, timeout=self._timeout, follow_redirects=True,
                                 transport=self._transport)

    @staticmethod
    def _check(response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        if response.status_code == 401:
            raise CanvasError("Canvas rejected the access token (it may be expired or revoked)", 401)
        if response.status_code == 403:
            raise CanvasError("This Canvas account is not allowed to see that (403)", 403)
        if response.status_code == 404:
            raise CanvasError("Not found in Canvas (404)", 404)
        raise CanvasError(f"Canvas returned HTTP {response.status_code}", response.status_code)

    async def _get(self, path: str, params: dict[str, Any] | list[tuple[str, Any]] | None = None) -> Any:
        try:
            async with self._client() as client:
                response = await client.get(f"{self.base_url}/api/v1{path}", params=params)
                self._check(response)
                return response.json()
        except httpx.HTTPError as exc:
            raise CanvasError(f"Could not reach Canvas: {type(exc).__name__}") from exc

    async def _pages(self, path: str, params: list[tuple[str, Any]]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        url: str | None = f"{self.base_url}/api/v1{path}"
        query: list[tuple[str, Any]] | None = [*params, ("per_page", 100)]
        try:
            async with self._client() as client:
                for _ in range(_MAX_PAGES):
                    if url is None:
                        break
                    response = await client.get(url, params=query)
                    self._check(response)
                    page = response.json()
                    items.extend(item for item in page if isinstance(item, dict))
                    found = _NEXT.search(response.headers.get("link", ""))
                    url, query = (found.group(1), None) if found else (None, None)
        except httpx.HTTPError as exc:
            raise CanvasError(f"Could not reach Canvas: {type(exc).__name__}") from exc
        return items

    async def me(self) -> dict[str, Any]:
        return await self._get("/users/self")

    async def courses(self) -> list[dict[str, Any]]:
        return await self._pages("/courses", [("enrollment_state", "active"), ("include[]", "term")])

    async def course(self, course_id: int | str) -> dict[str, Any]:
        return await self._get(f"/courses/{course_id}")

    async def assignments(self, course_id: int | str) -> list[dict[str, Any]]:
        return await self._pages(f"/courses/{course_id}/assignments", [("order_by", "due_at")])

    async def assignment(self, course_id: int | str, assignment_id: int | str) -> dict[str, Any]:
        return await self._get(f"/courses/{course_id}/assignments/{assignment_id}")

    async def submissions(self, course_id: int | str, assignment_id: int | str) -> tuple[list[dict[str, Any]], str]:
        """Every submission this token may see, and whose: ``class`` for a tutor, ``own`` for a student.

        Listing an assignment's submissions needs grading rights; a student gets 403 there and
        can only read their own (for a group assignment, the group's) submission.
        """

        path = f"/courses/{course_id}/assignments/{assignment_id}/submissions"
        try:
            return await self._pages(path, [("include[]", "user")]), "class"
        except CanvasError as exc:
            if exc.status != 403:
                raise
        own = await self._get(f"{path}/self", [("include[]", "user")])
        return ([own] if isinstance(own, dict) else []), "own"

    async def download(self, url: str) -> bytes:
        try:
            async with self._client() as client:
                async with client.stream("GET", url) as response:
                    self._check(response)
                    chunks, size = [], 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > _MAX_ATTACHMENT_BYTES:
                            raise CanvasError("A submission file is larger than 50 MB")
                        chunks.append(chunk)
                    return b"".join(chunks)
        except httpx.HTTPError as exc:
            raise CanvasError(f"Could not download a submission file: {type(exc).__name__}") from exc
