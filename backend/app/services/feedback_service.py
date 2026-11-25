"""Overall feedback on the report page: drafted by AI from the confirmed marks, approved by a tutor."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.analytics.service import AnalyticsUseCases
from app.config import Settings
from app.db.models.batch import Batch
from app.db.models.submission import Submission
from app.domain.states import BatchStatus
from app.llm import build_llm
from app.llm.usage import SQLAlchemyUsageSink, UsageRecord
from app.report import feedback as overall
from app.services.settings_service import load_ai_settings
from app.services.submission_service import marker_names


class FeedbackUseCases:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _editable(self, submission_id: str) -> tuple[Submission, Batch]:
        submission = self.session.get(Submission, submission_id)
        if submission is None:
            raise KeyError(submission_id)
        batch = self.session.get(Batch, submission.batch_id)
        if batch is None:
            raise KeyError(submission.batch_id)
        if batch.status == BatchStatus.FINALISED.value:
            raise RuntimeError("finalised_batch_locked")
        return submission, batch

    def _store(self, submission: Submission, value: dict[str, Any]) -> None:
        submission.feedback_json = json.dumps(value, ensure_ascii=False)
        self.session.commit()

    async def draft(self, submission_id: str, settings: Settings) -> dict[str, Any]:
        submission, batch = self._editable(submission_id)
        report = AnalyticsUseCases(self.session).submission_report(submission_id, "internal")
        runtime = settings.model_copy(deep=True)
        load_ai_settings(self.session, runtime)
        runtime.llm = batch.model_provider or runtime.llm
        runtime.ai_model = batch.model_name or runtime.ai_model
        started = time.perf_counter()
        text, response = await overall.draft(build_llm(runtime), report, {"submission_id": submission_id})
        SQLAlchemyUsageSink(self.session).record(UsageRecord(
            provider=runtime.llm, model=response.model or runtime.ai_model, purpose="feedback_draft",
            input_tokens=response.input_tokens, output_tokens=response.output_tokens,
            latency_ms=int((time.perf_counter() - started) * 1000), submission_id=submission_id,
            prompt_version=overall.PROMPT_VERSION, cached_tokens=response.cached_tokens,
        ))
        self._store(submission, {
            **text, "status": "draft", "source": "ai", "model": response.model or runtime.ai_model,
            "basis": overall.basis(report["criteria"]), "generated_at": datetime.now(timezone.utc).isoformat(),
        })
        return AnalyticsUseCases(self.session).submission_report(submission_id, "internal")

    def save(self, submission_id: str, payload: dict[str, Any], actor_id: str) -> dict[str, Any]:
        """A tutor's edit; with ``approve`` it becomes the feedback the student sees."""

        submission, _batch = self._editable(submission_id)
        report = AnalyticsUseCases(self.session).submission_report(submission_id, "internal")
        previous = json.loads(submission.feedback_json) if submission.feedback_json else {}
        text = overall.from_tutor(payload)
        if not text["summary"] and not any(text[field] for field in overall.FIELDS):
            submission.feedback_json = None  # cleared: the report shows no overall feedback
            self.session.commit()
            return AnalyticsUseCases(self.session).submission_report(submission_id, "internal")
        approve = bool(payload.get("approve"))
        value = {
            **text,
            "status": "approved" if approve else "draft",
            "source": previous.get("source", "tutor") if isinstance(previous, dict) else "tutor",
            "model": previous.get("model") if isinstance(previous, dict) else None,
            "basis": overall.basis(report["criteria"]),
            "generated_at": previous.get("generated_at") if isinstance(previous, dict) else None,
            "edited_at": datetime.now(timezone.utc).isoformat(),
        }
        if approve:
            value["approved_by"] = actor_id
            value["approved_by_name"] = marker_names(self.session).get(actor_id, actor_id)
            value["approved_at"] = value["edited_at"]
        self._store(submission, value)
        return AnalyticsUseCases(self.session).submission_report(submission_id, "internal")
