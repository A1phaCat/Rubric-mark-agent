"""Alembic migrations must run cleanly on a brand-new database.

0001 builds tables from the current models, so later migrations that add columns must
skip columns that already exist. Each check runs Alembic in its own process against a
throwaway SQLite file, because the app settings bind the database URL at import time.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]


def _alembic(data_dir: Path, *args: str) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "MARKER_ENV": "test",
        "MARKER_DATA_DIR": str(data_dir),
        "MARKER_DATABASE_URL": f"sqlite:///{(data_dir / 'marker.sqlite3').as_posix()}",
        "PYTHONPATH": str(BACKEND),
    }
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", *args],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _columns(data_dir: Path, table: str) -> set:
    with sqlite3.connect(data_dir / "marker.sqlite3") as conn:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _assert_ok(result: subprocess.CompletedProcess) -> None:
    assert result.returncode == 0, result.stdout + result.stderr


def test_upgrade_head_on_empty_database(tmp_path: Path) -> None:
    _assert_ok(_alembic(tmp_path, "upgrade", "head"))
    assert "trace_json" in _columns(tmp_path, "ai_results")
    assert "description" in _columns(tmp_path, "rubric_criteria")


def test_upgrade_head_twice_is_a_no_op(tmp_path: Path) -> None:
    _assert_ok(_alembic(tmp_path, "upgrade", "head"))
    _assert_ok(_alembic(tmp_path, "upgrade", "head"))


def test_evidence_trace_column_added_to_database_without_it(tmp_path: Path) -> None:
    # A database that predates 0008 has no trace_json; upgrading must add it.
    _assert_ok(_alembic(tmp_path, "upgrade", "head"))
    _assert_ok(_alembic(tmp_path, "downgrade", "0007_unique_ai_result"))
    assert "trace_json" not in _columns(tmp_path, "ai_results")
    _assert_ok(_alembic(tmp_path, "upgrade", "head"))
    assert "trace_json" in _columns(tmp_path, "ai_results")
