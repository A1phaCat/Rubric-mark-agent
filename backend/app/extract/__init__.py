"""Document-to-canonical-text boundary; extracted versions are immutable.

TODO(extract): implement DEV-GUIDE §G6 without importing API, services, grading or report.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CanonicalDocument:
    submission_id: str
    version: int
    text: str
    page_count: int


class Extractor(Protocol):
    def extract(self, submission_id: str, source_path: str) -> CanonicalDocument: ...
