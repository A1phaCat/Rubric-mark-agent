from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.analytics.service import AnalyticsUseCases
from app.db.models.core import Term, User
from app.deps import get_current_user, get_db

router = APIRouter(prefix="/me", tags=["me"])


@router.get("")
def me(user: dict = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    terms = [{"id": item.id, "label": item.label} for item in db.query(Term).order_by(Term.id.desc())]
    return {"user": user, "term": terms[0] if terms else None}


@router.put("")
def update_me(
    payload: dict[str, Any], user: dict = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    """Rename the local account; the name is stored in the users table."""

    name = str(payload.get("name") or "").strip()
    if not name or len(name) > 80:
        raise HTTPException(status_code=422, detail="Name must be 1–80 characters")
    row = db.get(User, user["id"])
    if row is None:
        row = User(id=user["id"], name=name, email="", role=user.get("role") or "tutor")
        db.add(row)
    else:
        row.name = name
    db.commit()
    return me({"id": row.id, "name": row.name, "role": row.role}, db)


@router.get("/summary")
def summary(user: dict = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return AnalyticsUseCases(db).home_summary(user["id"])


@router.get("/queue")
def queue(limit: int = Query(5, ge=1, le=50), db: Session = Depends(get_db)) -> dict:
    return AnalyticsUseCases(db).home_queue(limit)
