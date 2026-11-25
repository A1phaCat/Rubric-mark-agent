"""Evaluation tests run against a throwaway data directory with the offline FakeLLM."""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_DATA = Path(tempfile.mkdtemp(prefix="marker-eval-tests-"))
os.environ.setdefault("MARKER_ENV", "test")
os.environ.setdefault("MARKER_DATA_DIR", str(_DATA))
os.environ.setdefault("MARKER_DATABASE_URL", f"sqlite:///{(_DATA / 'marker.sqlite3').as_posix()}")
for path in (ROOT, ROOT / "backend"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
