"""Per-model token prices and the cost of a call.

Prices live in a JSON table (``pricing.json`` next to this module by default, or the file
named by ``MARKER_PRICING_FILE``) so they can be updated without code changes. Every table
records where its prices came from and when they were checked. A model that is not in the
table is *unpriced*: its cost is ``None``, never a silent 0.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_TABLE = Path(__file__).with_name("pricing.json")
_PER = 1_000_000


@dataclass(frozen=True)
class ModelPrice:
    model: str
    input: float  # USD per 1M uncached input tokens
    cached_input: float  # USD per 1M input tokens read from the provider cache
    output: float  # USD per 1M output tokens (reasoning tokens included)
    source: str

    def cost(self, input_tokens: int, output_tokens: int, cached_tokens: int = 0) -> float:
        """Cached tokens are part of ``input_tokens`` (OpenAI-style usage), billed at the
        cache-read price; the rest of the input at the normal input price."""

        cached = max(0, min(int(cached_tokens or 0), int(input_tokens or 0)))
        uncached = max(0, int(input_tokens or 0) - cached)
        return (
            uncached * self.input
            + cached * self.cached_input
            + max(0, int(output_tokens or 0)) * self.output
        ) / _PER


@dataclass(frozen=True)
class PriceTable:
    currency: str
    checked_at: str
    sources: Dict[str, str]
    models: Dict[str, ModelPrice]
    path: str

    def price_for(self, model: Optional[str]) -> Optional[ModelPrice]:
        """Exact (case-insensitive) match, else the longest listed name the model starts
        with, so dated snapshots such as ``gpt-4.1-2025-04-14`` use the ``gpt-4.1`` price
        while ``gpt-4.1-mini`` keeps its own."""

        if not model:
            return None
        wanted = model.strip().lower()
        by_name = {name.lower(): price for name, price in self.models.items()}
        if wanted in by_name:
            return by_name[wanted]
        prefixes = [name for name in by_name if wanted.startswith(name + "-")]
        return by_name[max(prefixes, key=len)] if prefixes else None

    def cost(
        self, model: Optional[str], input_tokens: int, output_tokens: int, cached_tokens: int = 0
    ) -> Optional[float]:
        price = self.price_for(model)
        return None if price is None else price.cost(input_tokens, output_tokens, cached_tokens)

    def describe(self) -> Dict[str, Any]:
        return {
            "currency": self.currency,
            "unit": "per 1M tokens",
            "checked_at": self.checked_at,
            "sources": self.sources,
        }


def parse_table(data: Dict[str, Any], path: str = "<memory>") -> PriceTable:
    models = {}
    for name, row in (data.get("models") or {}).items():
        models[name] = ModelPrice(
            model=name,
            input=float(row["input"]),
            cached_input=float(row.get("cached_input", row["input"])),
            output=float(row["output"]),
            source=str(row.get("source", "")),
        )
    return PriceTable(
        currency=str(data.get("currency", "USD")),
        checked_at=str(data.get("checked_at", "unknown")),
        sources={str(k): str(v) for k, v in (data.get("sources") or {}).items()},
        models=models,
        path=path,
    )


@lru_cache(maxsize=8)
def _load(path: str, mtime: float) -> PriceTable:
    del mtime  # part of the cache key, so an edited file is re-read
    return parse_table(json.loads(Path(path).read_text(encoding="utf-8")), path)


def load_table(path: Optional[Path] = None) -> PriceTable:
    if path is None:
        from app.config import settings

        path = settings.pricing_file or DEFAULT_TABLE
    resolved = Path(path).resolve()
    return _load(str(resolved), resolved.stat().st_mtime)
