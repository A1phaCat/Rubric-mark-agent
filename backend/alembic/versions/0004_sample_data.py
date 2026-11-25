"""replace fixture-backed demo rows with database sample data

- add ``batches.is_sample`` and ``rubrics.is_sample`` so seeded samples can be replaced
  and told apart from the tutor's own work;
- add ``batches.pinned`` and ``rubrics.pinned``: pinned items are listed first. Existing
  rows start unpinned; new rows (and samples) start pinned;
- add ``submissions.feedback_json`` for the reviewed student-facing summary;
- drop ``submissions.is_mock`` and delete the legacy fixture batches whose rows only
  carried counts (no files, no extracted text, no AI results). The legacy library
  rubrics are flagged as samples so ``python -m app.sample.seed`` can replace them.

Revision ID: 0004_sample_data
Revises: 0003_evidence_coverage
"""

import sqlalchemy as sa

from alembic import op

revision = "0004_sample_data"
down_revision = "0003_evidence_coverage"
branch_labels = None
depends_on = None

LEGACY_BATCHES = ("bat_asgn2", "bat_asgn1", "bat_quiz3", "bat_quiz2")
LEGACY_RUBRICS = (
    "rub_criticalessay",
    "rub_literaturereview",
    "rub_shortanswer",
    "rub_finalproject",
    "rub_grouppresentation",
    "rub_reflectivejournal",
)


def _columns(bind, table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(bind).get_columns(table)}


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
    bind = op.get_bind()
    if "is_sample" not in _columns(bind, "batches"):
        op.add_column(
            "batches", sa.Column("is_sample", sa.Boolean(), nullable=False, server_default=sa.false())
        )
    if "is_sample" not in _columns(bind, "rubrics"):
        op.add_column(
            "rubrics", sa.Column("is_sample", sa.Boolean(), nullable=False, server_default=sa.false())
        )
    for table in ("batches", "rubrics"):
        if "pinned" not in _columns(bind, table):
            op.add_column(
                table, sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.false())
            )
    if "feedback_json" not in _columns(bind, "submissions"):
        op.add_column("submissions", sa.Column("feedback_json", sa.Text(), nullable=True))

    legacy = _in(LEGACY_BATCHES)
    submissions = f"SELECT id FROM submissions WHERE batch_id IN ({legacy})"
    results = f"SELECT id FROM ai_results WHERE submission_id IN ({submissions})"
    for statement in (
        f"DELETE FROM evidence WHERE ai_result_id IN ({results})",
        f"DELETE FROM ai_results WHERE submission_id IN ({submissions})",
        f"DELETE FROM reviews WHERE submission_id IN ({submissions})",
        f"DELETE FROM llm_calls WHERE submission_id IN ({submissions})",
        f"DELETE FROM jobs WHERE batch_id IN ({legacy})",
        f"DELETE FROM submissions WHERE batch_id IN ({legacy})",
        f"DELETE FROM files WHERE batch_id IN ({legacy})",
        f"DELETE FROM batches WHERE id IN ({legacy})",
        f"UPDATE rubrics SET is_sample = 1 WHERE id IN ({_in(LEGACY_RUBRICS)})",
    ):
        bind.execute(sa.text(statement))

    if "is_mock" in _columns(bind, "submissions"):
        with op.batch_alter_table("submissions") as batch:
            batch.drop_column("is_mock")


def downgrade() -> None:
    bind = op.get_bind()
    if "is_mock" not in _columns(bind, "submissions"):
        op.add_column(
            "submissions", sa.Column("is_mock", sa.Boolean(), nullable=False, server_default=sa.false())
        )
    with op.batch_alter_table("submissions") as batch:
        if "feedback_json" in _columns(bind, "submissions"):
            batch.drop_column("feedback_json")
    for table in ("rubrics", "batches"):
        columns = _columns(bind, table)
        with op.batch_alter_table(table) as batch:
            for column in ("pinned", "is_sample"):
                if column in columns:
                    batch.drop_column(column)
