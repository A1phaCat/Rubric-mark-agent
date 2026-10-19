from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models.core import AppSetting
from app.deps import get_db, get_settings
from app.llm import build_llm
from app.llm.protocol import ProviderError
from app.security.secrets import protect_secret, unprotect_secret

router = APIRouter(prefix="/settings", tags=["settings"])


def load_ai_settings(db: Session, settings: Settings) -> None:
    values = {item.key: item.value_encrypted for item in db.query(AppSetting).all()}
    settings.llm = values.get("ai.provider", settings.llm)
    settings.ai_model = values.get("ai.model", settings.ai_model)
    settings.ai_base_url = values.get("ai.base_url") or settings.ai_base_url
    protected_key = values.get("ai.api_key")
    if protected_key:
        settings.ai_api_key = unprotect_secret(protected_key)


def _store(db: Session, key: str, value: str) -> None:
    item = db.get(AppSetting, key)
    if item is None:
        db.add(AppSetting(key=key, value_encrypted=value))
    else:
        item.value_encrypted = value


def _ai(settings: Settings) -> dict[str, Any]:
    return {
        "provider": settings.llm,
        "model": settings.ai_model,
        "base_url": settings.ai_base_url,
        "uses_university_gateway": settings.llm in {"azure", "university", "fake"},
        "has_api_key": bool(settings.ai_api_key),
        "available_models": ["fake-marker-v1"] if settings.llm == "fake" else [],
    }


@router.get("/ai")
def get_ai(
    settings: Settings = Depends(get_settings), db: Session = Depends(get_db)
) -> dict:
    load_ai_settings(db, settings)
    return _ai(settings)


@router.put("/ai")
def put_ai(
    payload: dict[str, Any],
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> dict:
    with db.begin():
        if "provider" in payload:
            settings.llm = str(payload["provider"])
            _store(db, "ai.provider", settings.llm)
        if "model" in payload:
            settings.ai_model = str(payload["model"])
            _store(db, "ai.model", settings.ai_model)
        if "base_url" in payload:
            settings.ai_base_url = payload["base_url"] or None
            _store(db, "ai.base_url", settings.ai_base_url or "")
        if payload.get("api_key"):
            settings.ai_api_key = str(payload["api_key"])
            _store(db, "ai.api_key", protect_secret(settings.ai_api_key))
    return _ai(settings)


@router.post("/ai/test")
async def test_ai(
    payload: dict[str, Any] | None = None,
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> dict:
    import time

    load_ai_settings(db, settings)
    candidate = settings.model_copy(deep=True)
    if payload:
        candidate.llm = str(payload.get("provider") or candidate.llm)
        candidate.ai_model = str(payload.get("model") or candidate.ai_model)
        candidate.ai_base_url = payload.get("base_url") or candidate.ai_base_url
        candidate.ai_api_key = payload.get("api_key") or candidate.ai_api_key
    started = time.perf_counter()
    try:
        models = list(await build_llm(candidate).list_models())
        return {
            "ok": True,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "model": candidate.ai_model,
            "models": models,
            "message": "Provider connection succeeded",
        }
    except (ProviderError, ValueError, NotImplementedError) as exc:
        return {
            "ok": False,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "model": None,
            "models": [],
            "message": str(exc),
        }


@router.get("/canvas")
def get_canvas() -> dict:
    return {"enabled": False, "base_url": None, "has_token": False}


@router.put("/canvas")
def put_canvas() -> None:
    raise HTTPException(
        501,
        {
            "error": {
                "code": "feature_not_enabled",
                "message": "Canvas is not available in the local MVP",
                "details": None,
            }
        },
    )
