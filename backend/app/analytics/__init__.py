"""Read-only dashboard, result and CSV projections.

Analytics never owns source records. TODO(analytics): implement DEV-GUIDE §G12.
"""

from typing import Any, Protocol


class AnalyticsReader(Protocol):
    def home_summary(self, user_id: str) -> dict[str, Any]: ...
    def batch_results(self, batch_id: str) -> dict[str, Any]: ...
