"""evidence-check steps on each AI result

The tool-based evidence check records what it read, cited, searched and why it
stopped. Tutors see it on the review screen; it is never shown to students.

Revision ID: 0008_evidence_trace
Revises: 0007_unique_ai_result
"""

import sqlalchemy as sa

from alembic import op

revision = "0008_evidence_trace"
down_revision = "0007_unique_ai_result"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_results", sa.Column("trace_json", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("ai_results") as batch:
        batch.drop_column("trace_json")
