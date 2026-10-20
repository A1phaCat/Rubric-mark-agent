from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api import batches, files, me, rubrics, submissions
from app.api import settings as settings_api
from app.config import settings
from app.db.base import Base
from app.db.session import SessionLocal, engine


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings.runtime_paths()
    Base.metadata.create_all(engine)
    from app.services.settings_service import load_ai_settings

    with SessionLocal() as session:
        load_ai_settings(session, settings)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI-assisted marker",
        version="0.1.0",
        openapi_url="/api/v1/openapi.json",
        lifespan=lifespan,
    )
    api = "/api/v1"
    for router in (
        me.router,
        batches.router,
        files.router,
        submissions.router,
        rubrics.router,
        settings_api.router,
    ):
        app.include_router(router, prefix=api)

    root = Path(__file__).resolve().parents[2]
    frontend = (root / "frontend").resolve()
    app.mount("/prototype", StaticFiles(directory=root / "prototype", html=True), name="prototype")
    app.mount("/js", StaticFiles(directory=frontend / "js"), name="js")

    @app.exception_handler(HTTPException)
    async def http_error(_request: Request, exc: HTTPException) -> JSONResponse:
        if isinstance(exc.detail, dict) and "error" in exc.detail:
            content = exc.detail
        else:
            code = "not_found" if exc.status_code == 404 else "validation_error"
            content = {"error": {"code": code, "message": str(exc.detail), "details": None}}
        return JSONResponse(status_code=exc.status_code, content=content, headers=exc.headers)

    @app.exception_handler(Exception)
    async def unhandled(_request: Request, exc: Exception) -> JSONResponse:
        del exc
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "Unexpected server error",
                    "details": None,
                }
            },
        )

    @app.get("/healthz")
    def health() -> dict:
        paths = settings.runtime_paths()
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        heartbeat_path = paths["cache"] / "worker-heartbeat.json"
        heartbeat = (
            json.loads(heartbeat_path.read_text(encoding="utf-8"))
            if heartbeat_path.exists()
            else {"worker_id": settings.worker_id, "last_seen": None}
        )
        return {
            "status": "ok",
            "db": "ok",
            "data_dirs": {key: path.exists() for key, path in paths.items()},
            "worker": {"mode": "db_queue", **heartbeat},
        }

    @app.get("/")
    def home() -> FileResponse:
        return FileResponse(frontend / "pages" / "00-home.html")

    @app.get("/{name}.html")
    def page(name: str) -> FileResponse:
        target = (frontend / "pages" / f"{name}.html").resolve()
        if target.parent != (frontend / "pages").resolve() or not target.exists():
            return FileResponse(frontend / "pages" / "00-home.html", status_code=404)
        return FileResponse(target)

    @app.get("/account-menu.js")
    def account_menu() -> FileResponse:
        return FileResponse(frontend / "js" / "account-menu.js")

    @app.get("/rubric-library.js")
    def rubric_library() -> FileResponse:
        return FileResponse(frontend / "js" / "rubric-library.js")

    return app


app = create_app()
