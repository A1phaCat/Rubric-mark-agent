from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import delete

from app.config import settings
from app.db.base import Base
from app.db.models.audit import AuditLog
from app.db.models.batch import Batch
from app.db.models.core import AppSetting, Term, User
from app.db.models.job import Job
from app.db.models.llm import LLMCache, LLMCall
from app.db.models.review import Review
from app.db.models.rubric import Rubric, RubricCriterion
from app.db.models.submission import AIResult, Evidence, File, Submission
from app.db.session import SessionLocal, engine
from app.rubric.assessment import normalise_assessment_plan


def dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def load(name: str):
    return json.loads((settings.fixtures_dir / name).read_text(encoding="utf-8"))


def seed() -> None:
    Base.metadata.create_all(engine)
    rubrics = load("rubrics.json")
    batches = load("batches.json")
    submissions = load("submissions/index.json")
    with SessionLocal.begin() as session:
        for model in (
            Evidence,
            AIResult,
            Review,
            AuditLog,
            Job,
            LLMCall,
            LLMCache,
            Submission,
            File,
            Batch,
            RubricCriterion,
            Rubric,
            AppSetting,
            Term,
            User,
        ):
            session.execute(delete(model))
        session.flush()
        session.add_all(
            [
                User(
                    id="usr_jalvarez",
                    name="J. Alvarez",
                    email="j.alvarez@sydney.edu.au",
                    role="tutor",
                ),
                User(
                    id="usr_mokafor", name="M. Okafor", email="m.okafor@sydney.edu.au", role="tutor"
                ),
                Term(id="term_2026s2", label="Semester 2, 2026"),
                AppSetting(key="ai.provider", value_encrypted="university"),
                AppSetting(key="canvas.enabled", value_encrypted="false"),
            ]
        )
        session.flush()
        for item in rubrics:
            session.add(
                Rubric(
                    id=item["id"],
                    title=item["title"],
                    source=item["source"],
                    version=item["version"],
                    created_by="usr_jalvarez",
                    created_at=dt(item["created_at"]),
                    updated_at=dt(item["updated_at"]),
                )
            )
            for position, definition in enumerate(item["criteria"]):
                descriptions = [level["description"] for level in definition["levels"]]
                grading_mode, aspects = normalise_assessment_plan(definition)
                session.add(
                    RubricCriterion(
                        id=definition["id"],
                        rubric_id=item["id"],
                        rubric_version=item["version"],
                        position=position,
                        name=definition["name"],
                        weight=definition["weight"],
                        level_hd=descriptions[0],
                        level_di=descriptions[1],
                        level_cr=descriptions[2],
                        level_ps=descriptions[3],
                        level_fl=descriptions[4],
                        pts_hd=definition["levels"][0].get("points"),
                        pts_di=definition["levels"][1].get("points"),
                        pts_cr=definition["levels"][2].get("points"),
                        pts_ps=definition["levels"][3].get("points"),
                        pts_fl=definition["levels"][4].get("points"),
                        levels_json=json.dumps(definition["levels"], ensure_ascii=False),
                        grading_mode=grading_mode,
                        aspects_json=json.dumps(aspects, ensure_ascii=False),
                        flags_json="[]",
                    )
                )
        session.flush()
        rubric_by_batch = {
            "bat_asgn2": rubrics[0],
            "bat_asgn1": rubrics[1],
            "bat_quiz3": rubrics[2],
            "bat_quiz2": rubrics[2],
        }
        for item in batches:
            session.add(
                Batch(
                    id=item["id"],
                    name=item["name"],
                    term_id=item["term"]["id"],
                    unit=item["unit"],
                    due_at=dt(item["due_at"]),
                    status=item["status"],
                    rubric_library_id=item["rubric"]["id"],
                    rubric_version=item["rubric"]["version"],
                    rubric_snapshot_json=json.dumps(rubric_by_batch[item["id"]]),
                    model_provider="fake",
                    model_name="fake-marker-v1",
                    prompt_version="criterion-grade-v1",
                    external_processing_acknowledged=False,
                    total_count=item["counts"]["total"],
                    created_by="usr_jalvarez",
                    created_at=dt(item["created_at"]),
                    started_at=dt(item["started_at"]),
                    completed_at=dt(item["completed_at"]),
                    finalised_at=dt(item["finalised_at"]),
                    version=item["version"],
                )
            )
        session.flush()
        for item in submissions:
            session.add(
                Submission(
                    id=item["id"],
                    batch_id=item["batch_id"],
                    file_id=None,
                    sid=item["sid"],
                    student_name=None,
                    status=item["status"],
                    error_reason=None,
                    word_count=2180 if not item["_mock"] else None,
                    text_quality="good" if item["status"] not in {"marking", "needs_ocr"} else None,
                    document_json=None,
                    document_version=1,
                    ai_total=item["ai_total"],
                    ai_level=None,
                    ai_summary=None,
                    min_confidence=item["confidence"],
                    final_total=item["final_total"],
                    final_level=None,
                    confirmed_by="usr_jalvarez" if item["status"] == "confirmed" else None,
                    confirmed_at=dt(NOW) if item["status"] == "confirmed" else None,
                    claimed_by=None,
                    claimed_until=None,
                    excluded_reason=None,
                    marker_id=item["marker"]["id"],
                    flags_json=json.dumps(item["flags"]),
                    is_mock=item["_mock"],
                    version=item["version"],
                    updated_at=dt(item["updated_at"]),
                )
            )
        # Reviews reference submissions directly. Flush the complete parent set first
        # because these models deliberately avoid ORM relationships in the domain layer.
        session.flush()
        for item in submissions:
            if item["status"] in {"ai_done", "in_review", "confirmed"}:
                rubric_item = rubric_by_batch[item["batch_id"]]
                for index, definition in enumerate(rubric_item["criteria"]):
                    weight = float(definition["weight"])
                    score = round(
                        weight
                        * (
                            0.8
                            if item["status"] != "confirmed"
                            else float(item["final_total"] or 70) / 100
                        ),
                        1,
                    )
                    session.add(
                        Review(
                            id=f"rev_{item['id'].removeprefix('sub_')}_{index + 1}",
                            submission_id=item["id"],
                            criterion_id=definition["id"],
                            score=score,
                            comment=""
                            if item["status"] != "confirmed"
                            else "Confirmed demo criterion.",
                            status="confirmed" if item["status"] == "confirmed" else "ai_suggested",
                            updated_by="usr_jalvarez",
                            updated_at=dt(item["updated_at"]),
                            version=1,
                        )
                    )
        session.flush()
        for item in submissions:
            if item["batch_id"] in {"bat_asgn2", "bat_asgn1"} and not item["_mock"]:
                submission_id = item["id"]
                path = settings.fixtures_dir / "reviews" / f"{submission_id}.json"
                review = json.loads(path.read_text(encoding="utf-8"))
                for result_index, criterion_result in enumerate(review["rubric"]["criteria"]):
                    result_id = f"air_{submission_id.removeprefix('sub_')}_{result_index + 1}"
                    session.add(
                        AIResult(
                            id=result_id,
                            submission_id=submission_id,
                            criterion_id=criterion_result["definition"]["id"],
                            level="DI",
                            score=criterion_result["ai_score"],
                            rationale=criterion_result["rationale"],
                            minor_json="[]",
                            coverage_json="[]",
                            sufficiency="unknown",
                            confidence=criterion_result["confidence"],
                            self_confidence=None,
                            provider="fake",
                            model="fake-marker-v1",
                            prompt_version="criterion-grade-v1",
                            input_tokens=0,
                            output_tokens=0,
                            latency_ms=0,
                            created_at=dt(NOW),
                        )
                    )
                    for evidence_index, evidence in enumerate(
                        [
                            e
                            for e in review["evidence"]
                            if e["criterion_id"] == criterion_result["definition"]["id"]
                        ]
                    ):
                        session.add(
                            Evidence(
                                id=f"evd_{submission_id.removeprefix('sub_')}_{result_index + 1}_{evidence_index + 1}",
                                ai_result_id=result_id,
                                role=evidence["label"],
                                quote=evidence["quote"],
                                page=evidence["page"],
                                para=evidence["paragraph"],
                                char_start=evidence["start_offset"],
                                char_end=evidence["end_offset"],
                                document_version=evidence["document_version"],
                                valid=True,
                            )
                        )
    print(
        f"Seeded {len(rubrics)} rubrics, {len(batches)} batches and {len(submissions)} submissions"
    )


NOW = "2026-10-18T01:00:00Z"


if __name__ == "__main__":
    seed()
