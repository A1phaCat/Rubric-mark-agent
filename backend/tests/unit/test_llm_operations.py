import asyncio

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models.llm import LLMCall
from app.llm.openai_compatible import response_text
from app.llm.ratelimit import RateLimiter
from app.llm.usage import SQLAlchemyUsageSink, UsageRecord


def test_rate_limiter_serialises_acquisition() -> None:
    limiter = RateLimiter(1000)

    async def run() -> None:
        await asyncio.gather(limiter.acquire(), limiter.acquire())

    asyncio.run(run())


def test_usage_sink_persists_metadata_without_prompt_content() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory.begin() as session:
        SQLAlchemyUsageSink(session).record(
            UsageRecord(
                provider="fake",
                model="fake-marker-v1",
                purpose="criterion_grade",
                input_tokens=12,
                output_tokens=4,
                latency_ms=1,
                submission_id="sub_test",
                prompt_version="criterion-grade-v1",
            )
        )
        assert session.scalar(select(func.count()).select_from(LLMCall)) == 1


def test_openai_compatible_response_accepts_reasoning_content_fallback() -> None:
    assert (
        response_text(
            {
                "message": {"reasoning_content": 'analysis followed by {"score": 1.5}'},
                "finish_reason": "stop",
            }
        )
        == 'analysis followed by {"score": 1.5}'
    )


def test_openai_compatible_response_flattens_content_parts() -> None:
    assert response_text({"message": {"content": [{"text": "{"}, {"text": "}"}]}}) == "{}"
