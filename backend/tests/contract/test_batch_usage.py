"""GET /batches/{id}/usage: tokens and cost per call, per submission and per batch."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.db.models.llm import LLMCall
from app.db.models.submission import Submission
from app.db.session import SessionLocal
from app.llm.usage import SQLAlchemyUsageSink, UsageRecord
from app.main import app
from app.sample.seed import seed

BATCH = "bat_sample_asgn2"
PURPOSES = ("usage_test_grade", "usage_test_check")


def _record(session, submission_id: str, model: str, purpose: str, tokens: tuple) -> None:
    SQLAlchemyUsageSink(session).record(
        UsageRecord(
            provider="openai",
            model=model,
            purpose=purpose,
            input_tokens=tokens[0],
            output_tokens=tokens[1],
            cached_tokens=tokens[2],
            latency_ms=1000,
            submission_id=submission_id,
            prompt_version="test",
        )
    )


@pytest.fixture()
def client():
    seed()
    with SessionLocal() as session:
        ids = list(
            session.scalars(
                select(Submission.id).where(Submission.batch_id == BATCH).order_by(Submission.id)
            )
        )[:2]
        session.execute(delete(LLMCall).where(LLMCall.submission_id.in_(ids)))
        _record(session, ids[0], "gpt-4.1", PURPOSES[0], (1000, 500, 200))  # $0.0057
        _record(session, ids[0], "gpt-4.1", PURPOSES[1], (2000, 0, 0))  # $0.004
        _record(session, ids[1], "gpt-4.1-2025-04-14", PURPOSES[0], (1000, 500, 200))  # $0.0057
        session.commit()
    yield TestClient(app), ids
    with SessionLocal() as session:
        session.execute(delete(LLMCall).where(LLMCall.purpose.in_(PURPOSES)))
        session.commit()


def test_cost_is_stored_on_each_call_not_zero(client) -> None:
    with SessionLocal() as session:
        costs = sorted(
            session.scalars(select(LLMCall.cost_usd).where(LLMCall.purpose.in_(PURPOSES)))
        )
    assert costs == pytest.approx([0.004, 0.0057, 0.0057])


def test_batch_usage_totals_per_submission_and_per_call(client) -> None:
    http, ids = client
    body = http.get(f"/api/v1/batches/{BATCH}/usage?include=calls").json()
    totals = body["totals"]
    assert totals["calls"] == 3 and totals["unpriced_calls"] == 0
    assert totals["input_tokens"] == 4000 and totals["cached_tokens"] == 400
    assert totals["output_tokens"] == 1000
    assert totals["cost_usd"] == pytest.approx(0.0154)
    assert totals["submissions_with_calls"] == 2
    assert totals["cost_per_submission_usd"] == pytest.approx(0.0077)
    assert totals["max_submission_cost_usd"] == pytest.approx(0.0097)
    assert totals["cost_per_call_usd"] == pytest.approx(0.0154 / 3, abs=1e-6)
    per_sub = {item["submission_id"]: item["cost_usd"] for item in body["submissions"]}
    assert per_sub == pytest.approx({ids[0]: 0.0097, ids[1]: 0.0057})
    assert len(body["calls"]) == 3 and all(call["cost_usd"] for call in body["calls"])
    assert body["pricing"]["checked_at"] and body["pricing"]["currency"] == "USD"
    assert "openai" in body["pricing"]["sources"]


def test_unpriced_model_withholds_the_total_instead_of_reporting_zero(client) -> None:
    http, ids = client
    with SessionLocal() as session:
        _record(session, ids[1], "my-azure-deployment", PURPOSES[1], (1000, 100, 0))
        session.commit()
    body = http.get(f"/api/v1/batches/{BATCH}/usage").json()
    assert body["pricing"]["unpriced_models"] == ["my-azure-deployment"]
    assert body["totals"]["unpriced_calls"] == 1
    assert body["totals"]["cost_usd"] is None
    assert body["totals"]["priced_cost_usd"] == pytest.approx(0.0154)
    assert "calls" not in body


def test_unknown_batch_is_404(client) -> None:
    http, _ = client
    assert http.get("/api/v1/batches/bat_missing/usage").status_code == 404
