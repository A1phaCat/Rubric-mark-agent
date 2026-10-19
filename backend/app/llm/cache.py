"""Cache contract; the DB implementation owns llm_cache rows."""

from __future__ import annotations

from typing import Protocol


class LLMCache(Protocol):
    def get(self, key: str) -> str | None: ...
    def put(self, key: str, response_json: str) -> None: ...
