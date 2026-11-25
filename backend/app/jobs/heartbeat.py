"""The worker's heartbeat file: who is working, and how many evidence agents are running."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import Settings

FRESH_SECONDS = 10


def path(settings: Settings) -> Path:
    return settings.runtime_paths()["cache"] / "worker-heartbeat.json"


def write(settings: Settings, evidence_agents: dict[str, int]) -> None:
    target = path(settings)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({
            "worker_id": settings.worker_id,
            "concurrency": settings.worker_concurrency,
            "last_seen": datetime.now(timezone.utc).isoformat(),
            "evidence_agents": evidence_agents,
        }),
        encoding="utf-8",
    )
    temporary.replace(target)  # readers never see a half-written file


def evidence_agents(settings: Settings, now: datetime | None = None) -> dict[str, int] | None:
    """Running evidence agents per submission, or None when the worker has not reported recently."""

    try:
        beat: dict[str, Any] = json.loads(path(settings).read_text(encoding="utf-8"))
        seen = datetime.fromisoformat(str(beat["last_seen"]))
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if ((now or datetime.now(timezone.utc)) - seen).total_seconds() > FRESH_SECONDS:
        return None
    agents = beat.get("evidence_agents")
    return {str(key): int(value) for key, value in agents.items()} if isinstance(agents, dict) else {}
