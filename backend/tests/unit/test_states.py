import pytest

from app.domain.states import (
    BATCH_TRANSITIONS,
    SUBMISSION_TRANSITIONS,
    BatchStatus,
    SubmissionStatus,
    can_transition,
    require_transition,
)


def test_batch_happy_path_and_reopen() -> None:
    path = [
        BatchStatus.DRAFT,
        BatchStatus.PROCESSING,
        BatchStatus.IN_REVIEW,
        BatchStatus.COMPLETED,
        BatchStatus.FINALISED,
        BatchStatus.COMPLETED,
    ]
    assert all(can_transition(a, b, BATCH_TRANSITIONS) for a, b in zip(path, path[1:]))


def test_failed_all_can_resume_processing() -> None:
    assert can_transition(BatchStatus.FAILED_ALL, BatchStatus.PROCESSING, BATCH_TRANSITIONS)


def test_ai_done_enters_review_on_open() -> None:
    assert can_transition(
        SubmissionStatus.AI_DONE, SubmissionStatus.IN_REVIEW, SUBMISSION_TRANSITIONS
    )


def test_ocr_failure_can_retry_or_exclude() -> None:
    assert can_transition(
        SubmissionStatus.OCR_FAILED, SubmissionStatus.OCR_RUNNING, SUBMISSION_TRANSITIONS
    )
    assert can_transition(
        SubmissionStatus.OCR_FAILED, SubmissionStatus.EXCLUDED, SUBMISSION_TRANSITIONS
    )


def test_invalid_transition_raises() -> None:
    with pytest.raises(ValueError, match="Invalid transition"):
        require_transition(BatchStatus.DRAFT, BatchStatus.FINALISED, BATCH_TRANSITIONS)
