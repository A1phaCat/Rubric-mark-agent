from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.canvas import CanvasError
from app.config import Settings
from app.db.models.core import AppSetting
from app.deps import get_db, get_settings
from app.llm import build_llm
from app.llm.protocol import ProviderError
from app.security.secrets import protect_secret
from app.services import canvas_service
from app.services.settings_service import load_ai_settings

router = APIRouter(prefix="/settings", tags=["settings"])


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
        "uses_university_gateway": settings.llm in {"azure", "university"},
        "has_api_key": bool(settings.ai_api_key),
        "available_models": [],
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
    provider = str(payload.get("provider", settings.llm))
    if provider == "fake" and not settings.fake_llm_allowed:
        raise HTTPException(
            422,
            {
                "error": {
                    "code": "validation_error",
                    "message": "The offline FakeLLM is available only in the test environment",
                    "details": None,
                }
            },
        )
    model = str(payload.get("model", settings.ai_model))
    base_url = payload.get("base_url", settings.ai_base_url) or None
    api_key = str(payload["api_key"]) if payload.get("api_key") else None
    protected_key = protect_secret(api_key) if api_key else None
    with db.begin():
        if "provider" in payload:
            _store(db, "ai.provider", provider)
        if "model" in payload:
            _store(db, "ai.model", model)
        if "base_url" in payload:
            _store(db, "ai.base_url", base_url or "")
        if protected_key is not None:
            _store(db, "ai.api_key", protected_key)
    settings.llm = provider
    settings.ai_model = model
    settings.ai_base_url = base_url
    if api_key is not None:
        settings.ai_api_key = api_key
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
        llm = build_llm(candidate)
        models = list(await llm.list_models())
        offered = bool(candidate.ai_model) and (not models or candidate.ai_model in models)
        if offered:
            # Listing models only proves the key works; one tiny request proves the model accepts
            # the parameters grading sends.
            await llm.complete(purpose="connection_test", prompt='Reply with the JSON {"ok": true} only.')
        return {
            "ok": True,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "model": candidate.ai_model if offered else None,
            "models": models,
            "message": "Provider connection succeeded" if offered
            else "Connected. Choose a model from this provider's list, then test again.",
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
def get_canvas(db: Session = Depends(get_db)) -> dict:
    return canvas_service.settings_view(db)


@router.put("/canvas")
def put_canvas(payload: dict[str, Any], db: Session = Depends(get_db)) -> dict:
    try:
        return canvas_service.save_settings(db, payload)
    except CanvasError as exc:
        raise HTTPException(422, {"error": {"code": "validation_error", "message": str(exc), "details": None}}) from exc


@router.post("/canvas/test")
async def test_canvas(payload: dict[str, Any] | None = None, db: Session = Depends(get_db)) -> dict:
    """Check the address and token with Canvas itself (the token's own profile)."""

    payload = payload or {}
    try:
        result = await canvas_service.test_connection(db, payload.get("base_url"), payload.get("token"))
    except CanvasError as exc:
        return {"ok": False, "user": None, "message": str(exc)}
    if not payload.get("token") or payload.get("save"):
        canvas_service.save_settings(db, {"user": result["user"]})
    return {**result, "message": f"Connected as {result['user']}"}
