"""Build an offline Canvas export folder for demos without Canvas credentials.

    python scripts/build_canvas_offline.py [--out data/canvas-offline]
    MARKER_CANVAS_OFFLINE_DIR=data/canvas-offline  # then restart the API

Uses the repository's Canvas rubric exports (backend/app/sample/rubrics/*.json, the shape
Canvas's API returns) and the synthetic sample submissions, laid out as
``submissions/<assignment_id>/<canvas_user_id>_<file>``. Grade pushes in offline mode are
appended to ``grade-pushes.jsonl`` in the folder; nothing leaves the machine.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.sample.seed import FILES, RUBRIC_FILES

# sample file token -> rubric export that file answers
PAIRS = {"ASGN1": "comp5348-asgn1.json", "ASGN2": "comp5348-asgn2.json"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=str(ROOT / "data" / "canvas-offline"))
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    exports = [p for p in sorted(RUBRIC_FILES.glob("*.json"))
               if isinstance(json.loads(p.read_text(encoding="utf-8")).get("rubric"), list)]
    for path in exports:
        shutil.copy(path, out / path.name)
    copied = 0
    for token, export_name in PAIRS.items():
        assignment_id = json.loads((RUBRIC_FILES / export_name).read_text(encoding="utf-8"))["assignment"]["id"]
        folder = out / "submissions" / str(assignment_id)
        folder.mkdir(parents=True, exist_ok=True)
        for index, file in enumerate(sorted(FILES.glob(f"*_{token}.*")), start=1):
            shutil.copy(file, folder / f"{9000 + index}_{file.name}")
            copied += 1
    print(f"{len(exports)} assignments with rubrics, {copied} submission files -> {out}")


if __name__ == "__main__":
    main()
