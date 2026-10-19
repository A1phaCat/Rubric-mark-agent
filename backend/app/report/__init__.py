"""Internal/student report composition and HTML/PDF rendering boundary.

TODO(report): implement DEV-GUIDE §G10. Student projections must omit AI/internal fields.
"""

from typing import Protocol


class ReportRenderer(Protocol):
    def render_html(self, submission_id: str, audience: str) -> str: ...
    def render_pdf(self, submission_id: str, audience: str) -> bytes: ...
