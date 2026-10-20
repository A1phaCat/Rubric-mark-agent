from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.analytics.service import AnalyticsUseCases
from app.db.models.core import Term
from app.deps import get_current_user, get_db

router = APIRouter(prefix="/me", tags=["me"])


@router.get("")
def me(user: dict = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    terms = [{"id": item.id, "label": item.label} for item in db.query(Term).order_by(Term.id.desc())]
    return {"user": user, "term": terms[0] if terms else None}


@router.get("/summary")
def summary(user: dict = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return AnalyticsUseCases(db).home_summary(user["id"])


@router.get("/queue")
def queue(limit: int = Query(5, ge=1, le=50), db: Session = Depends(get_db)) -> dict:
    return AnalyticsUseCases(db).home_queue(limit)
