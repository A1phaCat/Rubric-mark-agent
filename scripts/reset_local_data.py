"""Reset generated local MVP data while preserving saved AI provider settings."""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = (ROOT / "data").resolve()
DB_PATH = DATA_ROOT / "db" / "marker.sqlite3"
GENERATED_DIRS = (
    "uploads",
    "rubrics",
    "files",
    "extracted",
    "index",
    "reports",
    "exports",
    "cache",
    "logs",
)


def _settings() -> list[tuple[str, str]]:
    if not DB_PATH.exists():
        return []
    connection = sqlite3.connect(DB_PATH)
    try:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='settings'"
        ).fetchone()
        return (
            list(connection.execute("SELECT key, value_encrypted FROM settings"))
            if exists
            else []
        )
    finally:
        connection.close()


def _remove_generated_data() -> None:
    for suffix in ("", "-wal", "-shm"):
        target = Path(f"{DB_PATH}{suffix}").resolve()
        if target.parent != (DATA_ROOT / "db").resolve():
            raise RuntimeError(f"Refusing unsafe database target: {target}")
        target.unlink(missing_ok=True)
    for name in GENERATED_DIRS:
        target = (DATA_ROOT / name).resolve()
        if target.parent != DATA_ROOT:
            raise RuntimeError(f"Refusing unsafe generated-data target: {target}")
        if target.exists():
            shutil.rmtree(target)


def _run(*args: str, cwd: Path = ROOT) -> None:
    subprocess.run((sys.executable, *args), cwd=cwd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--yes",
        action="store_true",
        help="confirm deletion of generated batches, rubrics, submissions, jobs, and files",
    )
    args = parser.parse_args()
    if not args.yes:
        raise SystemExit(
            "Nothing deleted. Stop the dev server, then rerun with --yes to confirm the local reset."
        )

    saved_settings = _settings()
    _remove_generated_data()
    _run("-m", "alembic", "-c", "alembic.ini", "upgrade", "head", cwd=ROOT / "backend")
    _run("-m", "app.sample.seed", cwd=ROOT / "backend")

    if saved_settings:
        connection = sqlite3.connect(DB_PATH)
        try:
            connection.executemany(
                "INSERT OR REPLACE INTO settings (key, value_encrypted) VALUES (?, ?)",
                saved_settings,
            )
            connection.commit()
        finally:
            connection.close()
    print("Local generated data reset; sample data reloaded and AI provider settings preserved.")


if __name__ == "__main__":
    main()
