"""Configuration and the only runtime-path construction boundary."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="MARKER_", extra="ignore")

    env: str = "development"
    host: str = "127.0.0.1"
    port: int = 8000
    data_dir: Path = PROJECT_ROOT / "data"
    frontend_dir: Path = PROJECT_ROOT / "frontend"
    database_url: str = f"sqlite:///{(PROJECT_ROOT / 'data/db/marker.sqlite3').as_posix()}"
    llm: str = "university"
    timezone: str = "Australia/Sydney"
    worker_id: str = "local-worker-1"
    worker_concurrency: int = Field(default=3, ge=1, le=8)
    local_user_id: str = "usr_jalvarez"
    # Reload the sample batches on every API start so they can be marked again.
    reset_samples_on_start: bool = True
    job_lease_seconds: int = 60
    job_max_attempts: int = 3
    ai_base_url: str | None = None
    ai_api_key: str | None = Field(default=None, repr=False)
    ai_model: str = "gpt-4.1"
    ai_timeout_seconds: float = 120.0
    # Provider calls in flight across all worker slots and criteria (one shared limit).
    llm_max_in_flight: int = Field(default=6, ge=1, le=32)
    # Retries inside the LLM client for 429 / 5xx / timeouts; Retry-After is honoured.
    llm_max_retries: int = Field(default=5, ge=0, le=10)
    llm_max_backoff_seconds: float = Field(default=60.0, ge=1, le=600)
    # "full": the evidence step reads the whole submission (default). "retrieval": only the
    # passages retrieved for each criterion — kept for evaluation comparisons.
    grading_context: Literal["full", "retrieval"] = "full"
    # Model context window. A submission that cannot fit is routed to manual marking,
    # never truncated.
    ai_context_tokens: int = Field(default=128_000, ge=8_000)
    # Criteria of one submission graded at the same time (still bounded by llm_max_in_flight).
    criterion_concurrency: int = Field(default=3, ge=1, le=8)
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_threads: int = 2
    retrieval_candidate_limit: int = 12
    evidence_top_k: int = 5

    @property
    def fake_llm_allowed(self) -> bool:
        """The deterministic FakeLLM exists for automated tests only."""

        return self.env == "test"

    def runtime_paths(self) -> Dict[str, Path]:
        root = self.data_dir.resolve()
        paths = {
            "root": root,
            "db": root / "db",
            "uploads_tmp": root / "uploads" / "tmp",
            "rubrics_source": root / "rubrics" / "source",
            "files": root / "files",
            "extracted": root / "extracted",
            "index": root / "index",
            "reports": root / "reports",
            "exports": root / "exports",
            "cache": root / "cache",
            "logs": root / "logs",
        }
        for path in paths.values():
            path.mkdir(parents=True, exist_ok=True)
            if root not in (path, *path.parents):
                raise ValueError(f"Runtime path escaped data directory: {path}")
        return paths


settings = Settings()
