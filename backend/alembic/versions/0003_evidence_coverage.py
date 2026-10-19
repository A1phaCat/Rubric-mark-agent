"""persist rubric assessment plans and evidence coverage

Revision ID: 0003_evidence_coverage
Revises: 0002_variable_rubric_levels
"""

import json

import sqlalchemy as sa

from alembic import op
from app.rubric.assessment import normalise_assessment_plan

revision = "0003_evidence_coverage"
down_revision = "0002_variable_rubric_levels"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    rubric_columns = {
        column["name"] for column in sa.inspect(bind).get_columns("rubric_criteria")
    }
    if "grading_mode" not in rubric_columns:
        op.add_column(
            "rubric_criteria",
            sa.Column("grading_mode", sa.String(), nullable=False, server_default="holistic"),
        )
    if "aspects_json" not in rubric_columns:
        op.add_column(
            "rubric_criteria",
            sa.Column("aspects_json", sa.Text(), nullable=False, server_default="[]"),
        )

    rows = bind.execute(
        sa.text("SELECT id, name, levels_json FROM rubric_criteria")
    ).mappings()
    for row in rows:
        levels = json.loads(row["levels_json"] or "[]")
        mode, aspects = normalise_assessment_plan({"name": row["name"], "levels": levels})
        bind.execute(
            sa.text(
                "UPDATE rubric_criteria SET grading_mode=:mode, aspects_json=:aspects "
                "WHERE id=:criterion_id"
            ),
            {
                "mode": mode,
                "aspects": json.dumps(aspects, ensure_ascii=False),
                "criterion_id": row["id"],
            },
        )

    result_columns = {column["name"] for column in sa.inspect(bind).get_columns("ai_results")}
    if "coverage_json" not in result_columns:
        op.add_column(
            "ai_results",
            sa.Column("coverage_json", sa.Text(), nullable=False, server_default="{}"),
        )
    if "sufficiency" not in result_columns:
        op.add_column(
            "ai_results",
            sa.Column("sufficiency", sa.String(), nullable=False, server_default="unknown"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    result_columns = {column["name"] for column in sa.inspect(bind).get_columns("ai_results")}
    if "sufficiency" in result_columns:
        op.drop_column("ai_results", "sufficiency")
    if "coverage_json" in result_columns:
        op.drop_column("ai_results", "coverage_json")
    rubric_columns = {
        column["name"] for column in sa.inspect(bind).get_columns("rubric_criteria")
    }
    if "aspects_json" in rubric_columns:
        op.drop_column("rubric_criteria", "aspects_json")
    if "grading_mode" in rubric_columns:
        op.drop_column("rubric_criteria", "grading_mode")
