"""Lifecycle enums and transition rules from DEV-GUIDE §S10."""

from enum import Enum
from typing import Mapping, Set, TypeVar


class BatchStatus(str, Enum):
    DRAFT = "draft"
    PROCESSING = "processing"
    PAUSED = "paused"  # queued work held back; resumable (CANCELLED is not)
    IN_REVIEW = "in_review"
    COMPLETED = "completed"
    FINALISED = "finalised"
    FAILED_ALL = "failed_all"
    CANCELLED = "cancelled"


class SubmissionStatus(str, Enum):
    UPLOADED = "uploaded"
    EXTRACTING = "extracting"
    NEEDS_OCR = "needs_ocr"
    OCR_RUNNING = "ocr_running"
    OCR_FAILED = "ocr_failed"
    QUEUED = "queued"
    MARKING = "marking"
    AI_DONE = "ai_done"
    IN_REVIEW = "in_review"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    EXCLUDED = "excluded"
    CANCELLED = "cancelled"


class CriterionStatus(str, Enum):
    AI_SUGGESTED = "ai_suggested"
    EDITED = "edited"
    CONFIRMED = "confirmed"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


class Level(str, Enum):
    HD = "HD"
    DI = "DI"
    CR = "CR"
    PS = "PS"
    FL = "FL"


BATCH_TRANSITIONS: Mapping[BatchStatus, Set[BatchStatus]] = {
    BatchStatus.DRAFT: {BatchStatus.PROCESSING, BatchStatus.CANCELLED},
    BatchStatus.PROCESSING: {
        BatchStatus.IN_REVIEW,
        BatchStatus.FAILED_ALL,
        BatchStatus.CANCELLED,
        BatchStatus.PAUSED,
    },
    BatchStatus.PAUSED: {BatchStatus.PROCESSING, BatchStatus.IN_REVIEW, BatchStatus.CANCELLED},
    BatchStatus.IN_REVIEW: {BatchStatus.COMPLETED},
    BatchStatus.COMPLETED: {BatchStatus.FINALISED},
    BatchStatus.FINALISED: {BatchStatus.COMPLETED},
    BatchStatus.FAILED_ALL: {BatchStatus.PROCESSING},
    BatchStatus.CANCELLED: set(),
}

SUBMISSION_TRANSITIONS: Mapping[SubmissionStatus, Set[SubmissionStatus]] = {
    SubmissionStatus.UPLOADED: {SubmissionStatus.EXTRACTING, SubmissionStatus.EXCLUDED},
    SubmissionStatus.EXTRACTING: {
        SubmissionStatus.NEEDS_OCR,
        SubmissionStatus.QUEUED,
        SubmissionStatus.FAILED,
    },
    SubmissionStatus.NEEDS_OCR: {SubmissionStatus.OCR_RUNNING, SubmissionStatus.EXCLUDED},
    SubmissionStatus.OCR_RUNNING: {
        SubmissionStatus.QUEUED,
        SubmissionStatus.OCR_FAILED,
        SubmissionStatus.FAILED,
    },
    SubmissionStatus.OCR_FAILED: {
        SubmissionStatus.OCR_RUNNING,
        SubmissionStatus.EXCLUDED,
    },
    SubmissionStatus.QUEUED: {SubmissionStatus.MARKING, SubmissionStatus.FAILED},
    SubmissionStatus.MARKING: {SubmissionStatus.AI_DONE, SubmissionStatus.FAILED},
    SubmissionStatus.AI_DONE: {SubmissionStatus.IN_REVIEW, SubmissionStatus.EXCLUDED},
    SubmissionStatus.IN_REVIEW: {SubmissionStatus.CONFIRMED, SubmissionStatus.EXCLUDED},
    SubmissionStatus.CONFIRMED: {SubmissionStatus.IN_REVIEW},
    SubmissionStatus.FAILED: {SubmissionStatus.QUEUED, SubmissionStatus.EXCLUDED},
    SubmissionStatus.EXCLUDED: set(),
    SubmissionStatus.CANCELLED: set(),
}

CRITERION_TRANSITIONS: Mapping[CriterionStatus, Set[CriterionStatus]] = {
    CriterionStatus.AI_SUGGESTED: {CriterionStatus.EDITED, CriterionStatus.CONFIRMED},
    CriterionStatus.EDITED: {CriterionStatus.EDITED, CriterionStatus.CONFIRMED},
    CriterionStatus.CONFIRMED: {CriterionStatus.EDITED},
}

E = TypeVar("E", bound=Enum)


def can_transition(current: E, target: E, allowed: Mapping[E, Set[E]]) -> bool:
    return target in allowed.get(current, set())


def require_transition(current: E, target: E, allowed: Mapping[E, Set[E]]) -> None:
    if not can_transition(current, target, allowed):
        raise ValueError(f"Invalid transition: {current.value} -> {target.value}")
