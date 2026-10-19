"""Settings secret handling, upload guards, injection flags and redaction.

TODO(security): implement DEV-GUIDE §G15. Never log student/rubric text or keys.
"""

from typing import Protocol


class Redactor(Protocol):
    def redact(self, text: str) -> str: ...
