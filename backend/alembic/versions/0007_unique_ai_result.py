"""one AI result per submission criterion

With several worker slots, a job whose lease expired could be graded by two slots at
once. A unique index makes the second write fail instead of storing a duplicate.
Existing duplicates (if any) are reduced to the newest result first.

Revision ID: 0007_unique_ai_result
Revises: 0006_criterion_description
"""

import sqlalchemy as sa

from alembic import op

revision = "0007_unique_ai_result"
down_revision = "0006_criterion_description"
branch_labels = None
depends_on = None

_KEEP = (
    "SELECT id FROM (SELECT id, ROW_NUMBER() OVER (PARTITION BY submission_id, criterion_id "
    "ORDER BY created_at DESC, id DESC) AS n FROM ai_results) WHERE n = 1"
)


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text(f"DELETE FROM evidence WHERE ai_result_id NOT IN ({_KEEP})"))
    bind.execute(sa.text(f"DELETE FROM ai_results WHERE id NOT IN ({_KEEP})"))
    bind.execute(
        sa.text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_results_submission_criterion "
            "ON ai_results (submission_id, criterion_id)"
        )
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_ai_results_submission_criterion")
