from fastapi import APIRouter

from app.api.common import translate_error

router = APIRouter(prefix="/samples", tags=["samples"])


@router.post("/reset")
def reset_samples() -> dict:
    """Recreate the sample batches in their initial state (the tutor's own data is kept)."""

    from app.sample.seed import seed

    try:
        return {"reset": True, **seed()}
    except Exception as exc:
        raise translate_error(exc) from exc
