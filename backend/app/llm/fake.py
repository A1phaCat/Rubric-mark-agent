from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping, Sequence

from app.llm.protocol import LLMResponse


class FakeLLM:
    """Deterministic offline provider backed by recorded fixture outputs."""

    def __init__(self, fixture_dir: Path) -> None:
        self.fixture_dir = fixture_dir

    async def list_models(self) -> Sequence[str]:
        return ["fake-marker-v1"]

    async def complete(
        self, *, purpose: str, prompt: str, metadata: Mapping[str, str] | None = None
    ) -> LLMResponse:
        del prompt, metadata
        path = self.fixture_dir / f"{purpose}.json"
        if not path.exists():
            raise ValueError(f"No FakeLLM fixture for purpose: {purpose}")
        return LLMResponse(
            text=json.dumps(json.loads(path.read_text(encoding="utf-8"))), model="fake-marker-v1"
        )
