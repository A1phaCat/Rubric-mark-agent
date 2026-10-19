from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


from app.db.models import (  # noqa: E402,F401
    audit,
    batch,
    core,
    job,
    llm,
    review,
    rubric,
    submission,
)
