"""Cross-platform task runner used by Makefile and directly on Windows."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
ENV = {**os.environ, "PYTHONPATH": str(BACKEND)}
NPM = shutil.which("npm") or "npm"


def run(*args: str, cwd: Path = ROOT) -> None:
    print("+", " ".join(args), flush=True)
    subprocess.run(args, cwd=cwd, env=ENV, check=True)


def main() -> None:
    task = sys.argv[1] if len(sys.argv) > 1 else "help"
    if task == "api":
        run(
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--app-dir",
            str(BACKEND),
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        )
    elif task == "worker":
        run(sys.executable, "-m", "app.jobs.worker", cwd=BACKEND)
    elif task == "dev":
        api = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--app-dir",
                str(BACKEND),
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
            ],
            cwd=ROOT,
            env=ENV,
        )
        worker = subprocess.Popen(
            [sys.executable, "-m", "app.jobs.worker"], cwd=BACKEND, env=ENV
        )
        try:
            raise SystemExit(api.wait())
        finally:
            worker.terminate()
    elif task == "migrate":
        run(
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "alembic.ini",
            "upgrade",
            "head",
            cwd=BACKEND,
        )
    elif task == "seed":
        run(sys.executable, "-m", "app.sample.seed", cwd=BACKEND)
    elif task == "test":
        run(sys.executable, "-m", "pytest", "backend/tests", "tests/architecture", "-q")
    elif task == "lint":
        run(
            sys.executable,
            "-m",
            "ruff",
            "check",
            "backend/app",
            "backend/tests",
            "tests/architecture",
            "scripts",
        )
        run(
            sys.executable,
            "-m",
            "mypy",
            "backend/app/domain",
            "backend/app/llm/json_io.py",
        )
    elif task == "fmt":
        run(
            sys.executable,
            "-m",
            "ruff",
            "format",
            "backend/app",
            "backend/tests",
            "tests/architecture",
            "scripts",
        )
    elif task == "check":
        run(sys.executable, str(Path(__file__).resolve()), "lint")
        run(sys.executable, str(Path(__file__).resolve()), "test")
        if (ROOT / "node_modules").exists():
            run(NPM, "run", "test:e2e")
            run(NPM, "run", "test:visual")
        else:
            print("SKIP browser checks: run npm install first")
    else:
        print("tasks: dev api worker migrate seed test lint fmt check")


if __name__ == "__main__":
    main()
