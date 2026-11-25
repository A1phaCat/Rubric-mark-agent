"""Read-only Canvas LMS connection: courses, assignments with their rubrics, and submissions.

Nothing is ever written back to Canvas: final marks stay a tutor's decision in this app.
"""

from .client import CanvasClient, CanvasError, normalise_base_url

__all__ = ["CanvasClient", "CanvasError", "normalise_base_url"]
