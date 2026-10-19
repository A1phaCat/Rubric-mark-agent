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
    return {"id": "usr_jalvarez", "name": "J. Alvarez", "role": "tutor"}
