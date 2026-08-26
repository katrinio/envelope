"""Add financial pillow index.

Revision ID: 20260826_04
Revises: 20260826_03
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260826_04"
down_revision: str | Sequence[str] | None = "20260826_03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("envelopes") as batch_op:
        batch_op.add_column(
            sa.Column("pillow_index", sa.Integer(), server_default="2", nullable=False)
        )
        batch_op.create_check_constraint(
            "ck_envelopes_pillow_index_positive",
            "pillow_index > 0",
        )


def downgrade() -> None:
    with op.batch_alter_table("envelopes") as batch_op:
        batch_op.drop_constraint("ck_envelopes_pillow_index_positive", type_="check")
        batch_op.drop_column("pillow_index")
