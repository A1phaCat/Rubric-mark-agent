"""Provider settings persisted in the local database (secrets stay server-side)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models.core import AppSetting
from app.security.secrets import unprotect_secret


def load_ai_settings(db: Session, settings: Settings) -> None:
    """Overlay the provider choice saved in the settings table onto ``settings``."""

    values = {item.key: item.value_encrypted for item in db.query(AppSetting).all()}
    provider = values.get("ai.provider", settings.llm)
    # A FakeLLM choice saved by an older build is ignored outside the test environment.
    if provider != "fake" or settings.fake_llm_allowed:
        settings.llm = provider
    settings.ai_model = values.get("ai.model", settings.ai_model)
    settings.ai_base_url = values.get("ai.base_url") or settings.ai_base_url
    protected_key = values.get("ai.api_key")
    if protected_key:
        settings.ai_api_key = unprotect_secret(protected_key)
