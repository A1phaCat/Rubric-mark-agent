"""preserve variable rubric levels

Revision ID: 0002_variable_rubric_levels
Revises: 0001_initial
"""

import sqlalchemy as sa

from alembic import op

revision = "0002_variable_rubric_levels"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("rubric_criteria")}
    if "levels_json" not in columns:
        op.add_column("rubric_criteria", sa.Column("levels_json", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("rubric_criteria")}
    if "levels_json" in columns:
        op.drop_column("rubric_criteria", "levels_json")
