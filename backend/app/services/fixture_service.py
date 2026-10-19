from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class FixtureStore:
    """Read-only demo fixture adapter used by explicitly marked skeleton endpoints."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def read(self, relative: str) -> Any:
        return json.loads((self.root / relative).read_text(encoding="utf-8"))

    def batches(self) -> list[dict[str, Any]]:
        return self.read("batches.json")

    def rubrics(self) -> list[dict[str, Any]]:
        return self.read("rubrics.json")

    def submissions(self) -> list[dict[str, Any]]:
        return self.read("submissions/index.json")

    def batch(self, batch_id: str) -> dict[str, Any] | None:
        return next((item for item in self.batches() if item["id"] == batch_id), None)

    def submission(self, submission_id: str) -> dict[str, Any] | None:
        return next((item for item in self.submissions() if item["id"] == submission_id), None)
