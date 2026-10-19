from fastapi import APIRouter, Depends, Query, Response

from app.api.common import mock
from app.config import Settings
from app.deps import get_settings
from app.services.fixture_service import FixtureStore

router = APIRouter(prefix="/me", tags=["me"])


@router.get("/summary")
def summary(response: Response, settings: Settings = Depends(get_settings)) -> dict:
    return mock(response, FixtureStore(settings.fixtures_dir).read("home.json")["summary"])


@router.get("/queue")
def queue(
    response: Response,
    limit: int = Query(5, ge=1, le=50),
    settings: Settings = Depends(get_settings),
) -> dict:
    items = FixtureStore(settings.fixtures_dir).read("home.json")["queue"][:limit]
    return mock(response, {"items": items, "limit": limit})
