"""Timestamp formatting for the API: always ISO 8601 in UTC with an explicit offset."""

from datetime import datetime, timezone
from typing import Optional


def iso_utc(value: Optional[datetime]) -> Optional[str]:
    """SQLite returns naive datetimes for values written as UTC; label them as UTC."""

    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()
