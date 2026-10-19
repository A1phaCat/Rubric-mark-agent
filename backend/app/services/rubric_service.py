from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.batch import Batch
from app.db.models.rubric import Rubric, RubricCriterion
from app.domain.ids import new_id


class RubricUseCases:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(self, query: str | None = None, page: int = 1, page_size: int = 50) -> dict[str, Any]:
        statement = (
            select(Rubric).where(Rubric.archived_at.is_(None)).order_by(Rubric.updated_at.desc())
        )
        if query:
            statement = statement.where(Rubric.title.ilike(f"%{query}%"))
        rubrics = list(
            self.session.scalars(statement.offset((page - 1) * page_size).limit(page_size))
        )
        return {
            "items": [self._summary(item) for item in rubrics],
            "page": page,
            "page_size": page_size,
            "total": len(rubrics),
        }

    def get(self, rubric_id: str) -> dict[str, Any]:
        rubric = self.session.get(Rubric, rubric_id)
        if rubric is None or rubric.archived_at is not None:
            raise KeyError(rubric_id)
        criteria = list(
            self.session.scalars(
                select(RubricCriterion)
                .where(
                    RubricCriterion.rubric_id == rubric_id,
                    RubricCriterion.rubric_version == rubric.version,
                )
                .order_by(RubricCriterion.position)
            )
        )
        used = list(self.session.scalars(select(Batch).where(Batch.rubric_library_id == rubric_id)))
        return {
            "rubric": {
                **self._summary(rubric),
                "criteria": [self._criterion(item) for item in criteria],
                "created_at": rubric.created_at.isoformat(),
            },
            "used_by": [
                {"batch_id": b.id, "batch_name": b.name, "rubric_version": b.rubric_version}
                for b in used
            ],
        }

    def create(self, payload: dict[str, Any], actor_id: str) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        rubric_id = new_id("rub")
        rubric = Rubric(
            id=rubric_id,
            title=payload["title"],
            source=payload.get("source", "Manual"),
            version=1,
            created_by=actor_id,
            created_at=now,
            updated_at=now,
        )
        self.session.add(rubric)
        self._add_criteria(rubric_id, 1, payload["criteria"])
        self.session.flush()
        result = self.get(rubric_id)
        if payload.get("save_to_library") is False:
            rubric.archived_at = now
            self.session.flush()
        return result

    def update(self, rubric_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        rubric = self.session.get(Rubric, rubric_id)
        if rubric is None:
            raise KeyError(rubric_id)
        if payload["version"] != rubric.version:
            raise RuntimeError("version_conflict")
        rubric.version += 1
        rubric.title = payload["title"]
        rubric.source = payload.get("source", rubric.source)
        rubric.updated_at = datetime.now(timezone.utc)
        self._add_criteria(rubric_id, rubric.version, payload["criteria"])
        self.session.flush()
        return self.get(rubric_id)

    def delete(self, rubric_id: str, version: int) -> dict[str, Any]:
        rubric = self.session.get(Rubric, rubric_id)
        if rubric is None:
            raise KeyError(rubric_id)
        if rubric.version != version:
            raise RuntimeError("version_conflict")
        if self.session.scalar(
            select(func.count()).select_from(Batch).where(Batch.rubric_library_id == rubric_id)
        ):
            raise RuntimeError("rubric_in_use")
        rubric.archived_at = datetime.now(timezone.utc)
        return {"deleted": True, "rubric_id": rubric_id}

    def _add_criteria(self, rubric_id: str, version: int, criteria: list[dict[str, Any]]) -> None:
        for position, item in enumerate(criteria):
            levels = self._normalise_levels(item.get("levels", []), float(item["weight"]))
            descriptions = [level["description"] for level in levels]
            descriptions += [""] * (5 - len(descriptions))
            points = [float(level["points"]) for level in levels]
            points += [0.0] * (5 - len(points))
            self.session.add(
                RubricCriterion(
                    id=new_id("crt"),
                    rubric_id=rubric_id,
                    rubric_version=version,
                    position=position,
                    name=item["name"],
                    weight=float(item["weight"]),
                    level_hd=descriptions[0],
                    level_di=descriptions[1],
                    level_cr=descriptions[2],
                    level_ps=descriptions[3],
                    level_fl=descriptions[4],
                    pts_hd=points[0],
                    pts_di=points[1],
                    pts_cr=points[2],
                    pts_ps=points[3],
                    pts_fl=points[4],
                    levels_json=json.dumps(levels, ensure_ascii=False),
                    # Evidence requirements are submission-specific runtime
                    # data.  They are derived by the grading pipeline, not
                    # during rubric parsing or library persistence.
                    grading_mode=str(item.get("grading_mode") or ""),
                    aspects_json="[]",
                    flags_json=json.dumps(item.get("flags", [])),
                )
            )

    @staticmethod
    def _normalise_levels(levels: list[Any], weight: float) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        count = len(levels)
        for index, raw in enumerate(levels):
            if isinstance(raw, dict):
                label = str(raw.get("label") or raw.get("id") or f"Level {index + 1}")
                fallback = round(weight * (count - index) / count, 2) if index < count - 1 else 0
                points = float(raw.get("points", raw.get("max_score", fallback)))
                description = str(raw.get("description", ""))
                level_id = str(raw.get("id") or f"level-{index + 1}")
            else:
                label = f"Level {index + 1}"
                points = round(weight * (count - index) / count, 2) if index < count - 1 else 0
                description = str(raw)
                level_id = f"level-{index + 1}"
            result.append(
                {
                    **(raw if isinstance(raw, dict) else {}),
                    "id": level_id,
                    "label": label,
                    "points": points,
                    "min_score": float(raw.get("min_score", points)) if isinstance(raw, dict) else points,
                    "max_score": float(raw.get("max_score", points)) if isinstance(raw, dict) else points,
                    "min_inclusive": bool(raw.get("min_inclusive", True))
                    if isinstance(raw, dict)
                    else True,
                    "max_inclusive": bool(raw.get("max_inclusive", True))
                    if isinstance(raw, dict)
                    else True,
                    "description": description,
                }
            )
        return result

    def _summary(self, rubric: Rubric) -> dict[str, Any]:
        criteria_count = (
            self.session.scalar(
                select(func.count())
                .select_from(RubricCriterion)
                .where(
                    RubricCriterion.rubric_id == rubric.id,
                    RubricCriterion.rubric_version == rubric.version,
                )
            )
            or 0
        )
        total_weight = (
            self.session.scalar(
                select(func.sum(RubricCriterion.weight)).where(
                    RubricCriterion.rubric_id == rubric.id,
                    RubricCriterion.rubric_version == rubric.version,
                )
            )
            or 0
        )
        used_by_count = (
            self.session.scalar(
                select(func.count()).select_from(Batch).where(Batch.rubric_library_id == rubric.id)
            )
            or 0
        )
        return {
            "id": rubric.id,
            "version": rubric.version,
            "title": rubric.title,
            "source": rubric.source,
            "criteria_count": criteria_count,
            "total_weight": float(total_weight),
            "used_by_count": used_by_count,
            "updated_at": rubric.updated_at.isoformat(),
        }

    @staticmethod
    def _criterion(item: RubricCriterion) -> dict[str, Any]:
        if item.levels_json:
            levels = json.loads(item.levels_json)
        else:
            labels = ["HD", "DI", "CR", "PS", "FL"]
            descriptions = [item.level_hd, item.level_di, item.level_cr, item.level_ps, item.level_fl]
            points = [item.pts_hd, item.pts_di, item.pts_cr, item.pts_ps, item.pts_fl]
            levels = [
                {
                    "id": label.lower(),
                    "label": label,
                    "points": point if point is not None else item.weight,
                    "min_score": point if point is not None else 0,
                    "max_score": point if point is not None else item.weight,
                    "description": desc,
                }
                for label, desc, point in zip(labels, descriptions, points)
            ]
        return {
            "id": item.id,
            "name": item.name,
            "weight": item.weight,
            "description": "",
            "levels": levels,
            "grading_mode": item.grading_mode,
            "aspects": json.loads(item.aspects_json or "[]"),
        }
