"""Shared test configuration.

- The offline FakeLLM is only allowed when MARKER_ENV=test.
- Tests never touch the developer's data/ directory: the database and runtime files
  live in a throwaway directory created before any app module is imported.
"""

import os
import tempfile
from pathlib import Path

_DATA = Path(tempfile.mkdtemp(prefix="marker-tests-"))
os.environ.setdefault("MARKER_ENV", "test")
os.environ.setdefault("MARKER_DATA_DIR", str(_DATA))
os.environ.setdefault("MARKER_DATABASE_URL", f"sqlite:///{(_DATA / 'marker.sqlite3').as_posix()}")
