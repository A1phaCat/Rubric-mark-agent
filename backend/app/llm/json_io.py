"""Extract and validate structured output, with exactly one repair callback."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from jsonschema import ValidationError, validate

Repair = Callable[[str, str], str]


def extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL | re.IGNORECASE)
    if fenced:
        cleaned = fenced.group(1)
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError as error:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("No JSON object found") from error
        value = json.loads(cleaned[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("Structured output must be a JSON object")
    return value


def validate_json(
    text: str, schema: dict[str, Any], repair: Repair | None = None
) -> dict[str, Any]:
    try:
        value = extract_json(text)
        validate(value, schema)
        return value
    except (ValueError, json.JSONDecodeError, ValidationError) as first_error:
        if repair is None:
            raise ValueError(f"Invalid structured output: {first_error}") from first_error
        repaired = repair(text, str(first_error))
        try:
            value = extract_json(repaired)
            validate(value, schema)
            return value
        except (ValueError, json.JSONDecodeError, ValidationError) as second_error:
            raise ValueError(f"Repair failed: {second_error}") from second_error
