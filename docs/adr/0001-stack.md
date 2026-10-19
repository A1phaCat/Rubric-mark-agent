# ADR 0001: Local MVP stack

Status: accepted, 2026-10-18

Use FastAPI, SQLAlchemy/Alembic, SQLite WAL, vanilla HTML/CSS/JavaScript, pytest and Playwright. Heavy OCR/ML dependencies remain optional. This follows DEV-GUIDE §G1 while avoiding a frontend framework migration during the skeleton phase.

Consequences: developers can run one local API and one worker; the frozen prototype remains the visual baseline; later Postgres or framework adoption occurs behind stable contracts.

