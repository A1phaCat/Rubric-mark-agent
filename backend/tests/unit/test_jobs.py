import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models.job import Job
from app.jobs import worker as worker_module
from app.jobs.queue import JobQueue
from app.jobs.worker import handle


def test_enqueue_lease_heartbeat_and_done() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory.begin() as session:
        queued = JobQueue(session).enqueue(
            "grade", {"batch_id": "bat_test", "submission_id": "sub_test"}, run_after=datetime.now(timezone.utc)
        )
        assert queued.status == "queued"
    with session_factory.begin() as session:
        queue = JobQueue(session)
        leased = queue.lease("worker-test", 60)
        assert leased is not None and leased.status == "running"
        queue.heartbeat(leased, "worker-test", 60)
        queue.done(leased, "worker-test")
        assert leased.status == "done"


def test_failed_job_retries_then_exhausts_attempts() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory.begin() as session:
        queue = JobQueue(session)
        queue.enqueue("grade", {"submission_id": "sub_test"})
        job = queue.lease("worker-test", 60)
        assert job is not None
        queue.fail(job, "worker-test", "provider unavailable", max_attempts=2)
        assert job.status == "queued"
        job.run_after = datetime.now(timezone.utc)
        job = queue.lease("worker-test", 60)
        assert job is not None
        queue.fail(job, "worker-test", "provider unavailable", max_attempts=2)
        assert job.status == "failed"


def test_unknown_job_kind_is_rejected() -> None:
    import pytest

    with pytest.raises(ValueError):
        handle("demo_progress", {"batch_id": "bat_test"})


def test_worker_slots_lease_distinct_jobs_concurrently(tmp_path, monkeypatch) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'concurrent.sqlite3'}",
        connect_args={"check_same_thread": False, "timeout": 5},
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    with session_factory.begin() as session:
        for index in range(3):
            session.add(
                Job(
                    id=f"job_{index}",
                    kind="grade",
                    submission_id=f"sub_{index}",
                    batch_id="bat_test",
                    payload_json=json.dumps({"submission_id": f"sub_{index}"}),
                    status="queued",
                    attempts=0,
                    run_after=now,
                    created_at=now,
                    updated_at=now,
                )
            )

    barrier = threading.Barrier(3)
    handled: list[str] = []
    handled_lock = threading.Lock()

    def fake_handle(_kind: str, payload: dict[str, object]) -> None:
        with handled_lock:
            handled.append(str(payload["submission_id"]))
        barrier.wait(timeout=2)

    monkeypatch.setattr(worker_module, "SessionLocal", session_factory)
    monkeypatch.setattr(worker_module, "handle", fake_handle)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(worker_module.run_once, ["worker:1", "worker:2", "worker:3"]))

    assert results == [True, True, True]
    assert sorted(handled) == ["sub_0", "sub_1", "sub_2"]
    with session_factory() as session:
        jobs = list(session.scalars(select(Job).order_by(Job.id)))
    assert [job.status for job in jobs] == ["done", "done", "done"]
    assert {job.lease_owner for job in jobs} == {"worker:1", "worker:2", "worker:3"}


def test_active_job_renews_lease_during_long_provider_call(tmp_path, monkeypatch) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'heartbeat.sqlite3'}",
        connect_args={"check_same_thread": False, "timeout": 5},
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    with session_factory.begin() as session:
        session.add(
            Job(
                id="job_long",
                kind="grade",
                submission_id="sub_long",
                batch_id="bat_test",
                payload_json="{}",
                status="queued",
                attempts=0,
                run_after=now,
                created_at=now,
                updated_at=now,
            )
        )
    with session_factory.begin() as session:
        leased = JobQueue(session).lease("worker:1", 1)
        assert leased is not None

    monkeypatch.setattr(worker_module, "SessionLocal", session_factory)
    monkeypatch.setattr(worker_module.settings, "job_lease_seconds", 1)
    stop = threading.Event()
    heartbeat = threading.Thread(
        target=worker_module._renew_lease,
        args=("job_long", "worker:1", stop),
        daemon=True,
    )
    heartbeat.start()
    time.sleep(1.2)
    with session_factory.begin() as session:
        assert JobQueue(session).lease("worker:2", 1) is None
    stop.set()
    heartbeat.join(timeout=1)
