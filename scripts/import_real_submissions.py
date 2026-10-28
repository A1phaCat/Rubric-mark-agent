"""Import an external submission dataset into the marker database, de-identified.

    python scripts/import_real_submissions.py --source <folder or .zip> [--per-topic 30] [--topics REGEX]

Every PDF is read, its text de-identified (student numbers, names, e-mails, phone numbers →
keyed pseudonyms; see app.ingest.anonymise) and re-rendered as a new PDF, so no original file
or metadata ever reaches data/. Submissions are grouped into one batch per assignment and each
batch is paired with the closest library rubric (app.rubric.matching); the ranking and shared
terms are written to data/import/pairing.json. The salt lives in data/import/salt.bin.

Nothing here is committed: data/ is ignored by Git, and the source dataset must stay outside
the repository. Needs ``pip install -e "backend[import]"`` (reportlab).
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import secrets
import sys
import time
import zipfile
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.ingest.anonymise import AnonymisationReport, Anonymiser, residual_identifiers, strip_filename_sid  # noqa: E402
from app.rubric.matching import RubricCandidate, rank_rubrics  # noqa: E402

HEADER_UNIT = re.compile(r"^\s*Unit:\s*(.+)$", re.M)
HEADER_ROW = re.compile(r"^\s*Source CSV row:\s*(\d+)", re.M)
TOPIC_SUFFIX = re.compile(r"__[0-9a-f]{6,}$")
UNIT_CODE = re.compile(r"^((?:FIT|COMP|ELEC|SOFT)\d{4}(?:-(?:FIT|COMP)\d{4})*)")


@dataclass
class Item:
    topic: str
    title: str
    unit: str
    unit_name: str
    source_row: str
    sha256: str
    anon_pdf: str
    words: int
    redactions: dict[str, int]
    residual: int
    source_name: str = ""


def _pdf_entries(source: Path) -> Iterator[tuple[str, bytes]]:
    if source.suffix.lower() == ".zip":
        with zipfile.ZipFile(source) as archive:
            for info in archive.infolist():
                if info.filename.lower().endswith(".pdf") and "__MACOSX" not in info.filename:
                    yield info.filename, archive.read(info)
    else:
        for path in sorted(source.rglob("*.pdf")):
            yield str(path.relative_to(source)), path.read_bytes()


def _topic_of(relative: str) -> str:
    parts = Path(relative).parts
    # <collection>/<topic folder>/<file>.pdf or <collection>/<file>.pdf
    folder = parts[-2] if len(parts) >= 3 else Path(parts[-1]).stem.split("_row")[0].split("_", 1)[-1]
    return TOPIC_SUFFIX.sub("", folder)


def _extract(content: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(content))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


_LIST_START = re.compile(r"^(?:[-•*▪●]|\d+[.)]|[A-Za-z][.)]|#+ )\s*")


def _reflow(lines: list[str]) -> str:
    """Undo the PDF's visual line wrapping; keep list items, headings and short lines apart."""

    out = lines[0]
    for previous, line in zip(lines, lines[1:]):
        wrapped = len(previous) > 55 and not previous.endswith((".", ":", ";", "!", "?"))
        joinable = wrapped and not _LIST_START.match(line)
        out += (" " if joinable or (line[:1].islower() and not _LIST_START.match(line)) else "\n") + line
    return out


def _render(title: str, body: str) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    from xml.sax.saxutils import escape

    styles = getSampleStyleSheet()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
                            topMargin=2 * cm, bottomMargin=2 * cm, title=title,
                            author="anonymised", subject="De-identified submission", creator="marker-import")
    story: list[Any] = [Paragraph(escape(title), styles["Heading2"]), Spacer(1, 8)]
    for block in re.split(r"\n\s*\n", body):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if lines:
            story.append(Paragraph(escape(_reflow(lines)).replace("\n", "<br/>"), styles["BodyText"]))
            story.append(Spacer(1, 4))
    doc.build(story)
    return buffer.getvalue()


def _process(args: tuple[str, bytes, bytes, str, str | None]) -> dict[str, Any] | None:
    relative, content, salt, out_dir, forced_title = args
    text = _extract(content)
    if not text.strip():
        return None
    anonymiser = Anonymiser(salt)
    unit_match, row_match = HEADER_UNIT.search(text), HEADER_ROW.search(text)
    topic = _topic_of(relative)
    title = forced_title or text.strip().splitlines()[0].strip()
    source_row = row_match.group(1) if row_match else hashlib.sha256(content).hexdigest()[:12]
    body = text.split("\nSubmission", 1)[1] if "\nSubmission" in text and not forced_title else text
    report = AnonymisationReport()
    clean_title = anonymiser.text(title)
    clean_body = anonymiser.text(body, report)
    pseudo = anonymiser.student_number(f"{title}|{source_row}")
    pdf = _render(clean_title, clean_body)
    target = Path(out_dir) / hashlib.sha256(title.encode()).hexdigest()[:10] / f"SID-{pseudo}.pdf"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(pdf)
    unit_name = unit_match.group(1).strip() if unit_match else ""
    code = UNIT_CODE.match(title)
    return asdict(
        Item(
            topic=topic,
            title=clean_title,
            unit=code.group(1) if code else unit_name.split(" ")[0],
            unit_name=unit_name,
            source_row=source_row,
            sha256=hashlib.sha256(clean_body.encode()).hexdigest(),
            anon_pdf=str(target),
            source_name=anonymiser.text(strip_filename_sid(Path(relative).name)),
            words=len(clean_body.split()),
            redactions={k: v for k, v in asdict(report).items() if k != "tokens"},
            residual=len(residual_identifiers(clean_title + "\n" + clean_body)),
        )
    )


def _salt(path: Path) -> bytes:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(secrets.token_bytes(32))
        os.chmod(path, 0o600)
    return path.read_bytes()


def _rubric_candidates(session: Any) -> list[RubricCandidate]:
    from sqlalchemy import select

    from app.db.models.rubric import Rubric, RubricCriterion

    out = []
    for rubric in session.scalars(select(Rubric).where(Rubric.archived_at.is_(None))):
        criteria = session.scalars(
            select(RubricCriterion).where(RubricCriterion.rubric_id == rubric.id,
                                          RubricCriterion.rubric_version == rubric.version)
        )
        parts = [rubric.title]
        for c in criteria:
            parts += [c.name, c.description, c.level_hd, c.level_di, c.level_cr, c.level_ps, c.level_fl]
        out.append(RubricCandidate(rubric.id, rubric.title, "\n".join(p for p in parts if p)))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", required=True, type=Path, help="dataset folder or .zip (outside the repo)")
    parser.add_argument("--per-topic", type=int, default=0, help="keep at most N submissions per assignment (0 = all)")
    parser.add_argument("--topics", default=None, help="only assignments whose title matches this regex")
    parser.add_argument("--min-topic-size", type=int, default=1)
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    parser.add_argument("--title", default=None,
                        help="assignment title for PDFs without the dataset header (one batch for the folder)")
    parser.add_argument("--unit", default=None, help="unit code for --title imports")
    parser.add_argument("--rubric-id", default=None,
                        help="use this library rubric instead of the best match (the ranking is still recorded)")
    parser.add_argument("--replace", action="store_true", help="re-create batches that were imported before")
    args = parser.parse_args()

    source = args.source.resolve()
    if ROOT in (source, *source.parents):
        raise SystemExit("Keep the source dataset outside the repository")

    from app.config import settings

    paths = settings.runtime_paths()
    import_dir = paths["root"] / "import"
    salt = _salt(import_dir / "salt.bin")
    anon_dir = import_dir / "anonymised"
    started = time.time()
    entries = list(_pdf_entries(source))
    topic_filter = re.compile(args.topics) if args.topics else None
    seen: set[tuple[str, str]] = set()
    items: list[dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        work = ((rel, data, salt, str(anon_dir), args.title) for rel, data in entries)
        for result in pool.map(_process, work, chunksize=8):
            if result is None:
                continue
            key = (result["title"], result["source_row"])
            if key in seen or (topic_filter and not topic_filter.search(result["title"])):
                continue
            seen.add(key)
            items.append(result)
    by_title: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        by_title[item["title"]].append(item)
    print(f"read {len(entries)} PDFs → {len(items)} unique submissions in {len(by_title)} assignments "
          f"({time.time() - started:.0f}s)")

    from sqlalchemy import select

    from app.db.models.batch import Batch
    from app.db.models.submission import File, Submission
    from app.db.session import SessionLocal
    from app.sample import seed as sample_seed
    from app.services.batch_service import BatchUseCases
    from app.services.submission_service import apply_extraction, store_upload

    with SessionLocal.begin() as session:
        sample_seed._ensure_people(session)
    with SessionLocal.begin() as session:
        sample_seed._create_rubrics(session)
        candidates = _rubric_candidates(session)

    pairing: list[dict[str, Any]] = []
    totals = {"batches": 0, "submissions": 0, "skipped_existing": 0}
    redaction_totals: dict[str, int] = defaultdict(int)
    residual_total = 0
    roster: list[dict[str, Any]] = []
    actor = sample_seed.manifest.LOCAL_USER["id"]
    for title, group in sorted(by_title.items(), key=lambda kv: -len(kv[1])):
        if len(group) < args.min_topic_size:
            continue
        group.sort(key=lambda item: int(item["source_row"]) if item["source_row"].isdigit() else 0)
        chosen = group[: args.per_topic] if args.per_topic else group
        sample_texts = []
        for item in chosen[:3]:
            from pypdf import PdfReader

            sample_texts.append("\n".join(p.extract_text() or "" for p in PdfReader(item["anon_pdf"]).pages)[:20000])
        ranked = rank_rubrics(title, sample_texts, candidates)
        best = ranked[0]
        if args.rubric_id:
            forced = [m for m in ranked if m.rubric_id == args.rubric_id]
            if not forced:
                raise SystemExit(f"rubric {args.rubric_id} is not in the library")
            best = forced[0]
        if args.unit:
            for item in chosen:
                item["unit"] = args.unit
        batch_id = "bat_real_" + hashlib.sha256(title.encode()).hexdigest()[:12]
        pairing.append({
            "batch_id": batch_id, "assignment": title, "unit": chosen[0]["unit"],
            "submissions": len(chosen), "available": len(group),
            "rubric_id": best.rubric_id, "rubric_title": best.title, "score": best.score,
            "shared_terms": list(best.shared_terms), "genre": best.genre,
            "runner_up": [{"rubric_id": m.rubric_id, "score": m.score} for m in ranked[1:3]],
            "approximate": not args.rubric_id, "chosen_by": "operator (--rubric-id)" if args.rubric_id else "best match",
            "match_rank": [m.rubric_id for m in ranked].index(best.rubric_id) + 1,
            "basis": "TF-IDF cosine of assignment title (x5) + first 3 anonymised submissions vs rubric text, +0.2 when both titles name the same assessment genre (reflective, essay, proposal, ...)",
        })
        with SessionLocal.begin() as session:
            existing = session.get(Batch, batch_id)
            if existing is not None and not args.replace:
                totals["skipped_existing"] += 1
                continue
            if existing is not None:
                sample_seed._delete_batch_rows(session, existing)
                session.flush()
            batches = BatchUseCases(session)
            batches.create(
                {"name": f"{title} · anonymised", "unit": chosen[0]["unit"], "rubric_id": best.rubric_id,
                 "rubric_version": 1,
                 "due_at": (datetime.now(timezone.utc) + timedelta(days=14)).replace(microsecond=0).isoformat()},
                actor, batch_id=batch_id,
            )
            batch = session.get(Batch, batch_id)
            assert batch is not None
            batch.rubric_version = session.scalar(
                select(sample_seed.Rubric.version).where(sample_seed.Rubric.id == best.rubric_id)
            )
            batches.snapshot_rubric(batch)
            for item in chosen:
                path = Path(item["anon_pdf"])
                entry = store_upload(session, settings, batch, path.name, path.read_bytes())
                if entry.get("status") != "accepted":
                    continue
                submission = session.get(Submission, entry["submission_id"])
                stored_file = session.get(File, entry["id"])
                assert submission is not None and stored_file is not None
                apply_extraction(session, submission, stored_file)
                roster.append({"batch_id": batch_id, "submission_id": submission.id,
                               "sid": submission.sid, "source_name": item["source_name"]})
                totals["submissions"] += 1
                for key, value in item["redactions"].items():
                    redaction_totals[key] += value
                residual_total += item["residual"]
            totals["batches"] += 1
    summary = {
        "source": source.name, "pdfs_read": len(entries), "unique_submissions": len(items),
        "assignments": len(by_title), **totals, "redactions": dict(redaction_totals),
        "residual_identifier_matches": residual_total, "seconds": round(time.time() - started, 1),
        "pairing": pairing,
    }
    stem = re.sub(r"[^A-Za-z0-9]+", "-", source.stem).strip("-").lower()
    out = import_dir / f"pairing-{stem}.json"
    out.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    # pseudonymous submission ↔ anonymised source name, for eval joins (git-ignored, under data/)
    (import_dir / f"submissions-{stem}.json").write_text(json.dumps(roster, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "pairing"}, indent=2))
    print(f"pairing written to {out}")


if __name__ == "__main__":
    main()
