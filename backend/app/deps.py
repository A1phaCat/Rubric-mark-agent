"""FastAPI dependencies for configuration, DB sessions, and the local user."""

from collections.abc import Generator
from typing import Any

from sqlalchemy.orm import Session

from app.config import Settings, settings
from app.db.session import SessionLocal


def get_settings() -> Settings:
    return settings


def get_db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_current_user() -> dict[str, Any]:
    """The single local user (no authentication in the local MVP), read from the database."""

    from app.db.models.core import User

    with SessionLocal() as session:
        user = session.get(User, settings.local_user_id)
        if user is None:
            return {"id": settings.local_user_id, "name": "Local tutor", "role": "tutor"}
        return {"id": user.id, "name": user.name, "role": user.role}
