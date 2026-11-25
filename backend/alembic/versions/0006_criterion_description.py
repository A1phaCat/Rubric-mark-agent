"""store each rubric criterion's own description (what the criterion assesses)

Rubrics such as Canvas exports describe the criterion separately from its levels, and
some give levels as labels and points only — then this text is what the work is judged
against.

Revision ID: 0006_criterion_description
Revises: 0005_pin_limit
"""

import sqlalchemy as sa

from alembic import op

revision = "0006_criterion_description"
down_revision = "0005_pin_limit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("rubric_criteria")}
    if "description" not in columns:
        op.add_column("rubric_criteria", sa.Column("description", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    with op.batch_alter_table("rubric_criteria") as batch:
        batch.drop_column("description")
