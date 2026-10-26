"""cap pinned batches at three and order pins by when they were pinned

Revision ID: 0005_pin_limit
Revises: 0004_sample_data
"""

import sqlalchemy as sa

from alembic import op

revision = "0005_pin_limit"
down_revision = "0004_sample_data"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("batches")}
    if "pinned_at" not in columns:
        op.add_column("batches", sa.Column("pinned_at", sa.DateTime(timezone=True), nullable=True))
    bind.execute(sa.text("UPDATE batches SET pinned_at = created_at WHERE pinned = 1 AND pinned_at IS NULL"))
    # Keep only the three most recently created pins.
    bind.execute(
        sa.text(
            "UPDATE batches SET pinned = 0, pinned_at = NULL WHERE pinned = 1 AND id NOT IN "
            "(SELECT id FROM batches WHERE pinned = 1 ORDER BY pinned_at DESC LIMIT 3)"
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("batches") as batch:
        batch.drop_column("pinned_at")
