from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models.batch import Batch
from app.db.models.core import Term, User
from app.db.models.review import Review
from app.db.models.submission import Submission
from app.services.review_service import ReviewUseCases


def test_confirm_completes_batch_in_same_transaction() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    with factory.begin() as session:
        session.add_all(
            [
                User(id="usr_test", name="Test", email="test@example.test", role="tutor"),
                Term(id="term_test", label="Test"),
                Batch(
                    id="bat_test",
                    name="One",
                    term_id="term_test",
                    status="in_review",
                    total_count=1,
                    created_by="usr_test",
                    created_at=now,
                    version=1,
                ),
                Submission(
                    id="sub_test",
                    batch_id="bat_test",
                    sid="SID-1",
                    status="in_review",
                    flags_json="[]",
                    version=1,
                    updated_at=now,
                ),
                Review(
                    id="rev_test",
                    submission_id="sub_test",
                    criterion_id="crt_test",
                    score=80,
                    comment="Ready",
                    status="edited",
                    updated_by="usr_test",
                    updated_at=now,
                    version=1,
                ),
            ]
        )
    with factory.begin() as session:
        result = ReviewUseCases(session).confirm("sub_test", "usr_test", 1)
        assert result["batch_status"] == "completed"
        assert result["next_id"] is None
        assert session.get(Batch, "bat_test").status == "completed"
