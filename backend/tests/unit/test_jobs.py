from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.events.bus import event_bus
from app.jobs.queue import JobQueue
from app.jobs.worker import handle


def test_enqueue_lease_heartbeat_and_done() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory.begin() as session:
        queued = JobQueue(session).enqueue(
            "demo_progress", {"batch_id": "bat_demo"}, run_after=datetime.now(timezone.utc)
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


def test_demo_handler_publishes_batch_progress() -> None:
    queue = event_bus.subscribe("bat_demo")
    try:
        handle("demo_progress", {"batch_id": "bat_demo", "status": "processing"})
        event = queue.get_nowait()
        assert event["event"] == "batch_progress"
        assert event["data"]["batch_id"] == "bat_demo"
    finally:
        event_bus.unsubscribe("bat_demo", queue)
