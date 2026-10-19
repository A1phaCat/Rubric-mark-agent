from typing import Any

from fastapi import HTTPException, Response
from sqlalchemy.exc import OperationalError


def mock(response: Response, payload: dict[str, Any]) -> dict[str, Any]:
    response.headers["X-Mock"] = "true"
    return {**payload, "_mock": True}


def translate_error(exc: Exception) -> HTTPException:
    value = str(exc).strip("'")
    if isinstance(exc, OperationalError) and "database is locked" in value.lower():
        return HTTPException(
            503,
            {
                "error": {
                    "code": "database_busy",
                    "message": "The local database is briefly busy. Please retry the action.",
                    "details": None,
                }
            },
        )
    if isinstance(exc, KeyError):
        return HTTPException(
            404, {"error": {"code": "not_found", "message": value, "details": None}}
        )
    codes = {
        "version_conflict": 409,
        "rubric_in_use": 409,
        "invalid_transition": 409,
        "batch_incomplete": 409,
        "submission_locked": 423,
        "manifest_unresolved": 422,
        "batch_must_be_cancelled": 409,
        "finalised_batch_locked": 409,
    }
    return HTTPException(
        codes.get(value, 422),
        {
            "error": {
                "code": value if value in codes else "validation_error",
                "message": value,
                "details": None,
            }
        },
    )
