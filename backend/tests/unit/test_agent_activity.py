"""Live counts of running evidence agents: counted while an agent works, published by the worker."""

import json
from datetime import datetime, timedelta, timezone

from app.agent import activity
from app.config import Settings
from app.jobs import heartbeat
from tests.unit.test_agent_evidence import Scripted, _run, done
from tests.unit.test_full_text_grading import stored  # noqa: F401


def test_an_agent_is_counted_while_it_works_and_not_after() -> None:
    seen = []

    class Watching(Scripted):
        async def chat(self, **kwargs):
            seen.append(activity.snapshot())
            return await super().chat(**kwargs)

    _run(Watching((done(),)), metadata={"submission_id": "sub_a", "criterion_id": "c1"})
    assert seen and all(snapshot == {"sub_a": 1} for snapshot in seen)
    assert activity.snapshot() == {}


def test_counts_add_up_per_submission_and_ignore_unknown_ones() -> None:
    with activity.running("sub_a"), activity.running("sub_a"), activity.running("sub_b"), activity.running(None):
        assert activity.snapshot() == {"sub_a": 2, "sub_b": 1}
    assert activity.snapshot() == {}


def test_the_heartbeat_carries_the_counts_and_goes_stale(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path)
    settings.runtime_paths()["cache"].mkdir(parents=True, exist_ok=True)
    assert heartbeat.evidence_agents(settings) is None  # no worker has reported
    heartbeat.write(settings, {"sub_a": 3})
    assert heartbeat.evidence_agents(settings) == {"sub_a": 3}
    later = datetime.now(timezone.utc) + timedelta(seconds=heartbeat.FRESH_SECONDS + 1)
    assert heartbeat.evidence_agents(settings, now=later) is None
    beat = json.loads(heartbeat.path(settings).read_text(encoding="utf-8"))
    assert beat["concurrency"] == settings.worker_concurrency


def test_a_batch_shows_only_its_own_running_agents(stored, monkeypatch) -> None:  # noqa: F811
    from app.services import batch_service
    from app.services.batch_service import BatchUseCases

    monkeypatch.setattr(batch_service.heartbeat, "evidence_agents", lambda _settings: {"sub_t": 3, "sub_other": 2})
    with stored() as session:
        assert BatchUseCases(session).live_agents("bat_t") == {"evidence": 3}
    monkeypatch.setattr(batch_service.heartbeat, "evidence_agents", lambda _settings: None)
    with stored() as session:
        assert BatchUseCases(session).live_agents("bat_t") is None  # worker silent: no number shown
