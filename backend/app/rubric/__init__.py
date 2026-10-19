"""Rubric parsing and deterministic structural validation.

TODO(rubric): implement DEV-GUIDE §G3. Public API is parse() and validate().
"""

from typing import Any, Protocol


class RubricParser(Protocol):
    async def parse(self, text: str) -> dict[str, Any]: ...
    def validate(self, rubric: dict[str, Any]) -> list[str]: ...
