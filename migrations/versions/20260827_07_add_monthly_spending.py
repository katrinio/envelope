"""Add monthly spending pool and planned items.

Revision ID: 20260827_07
Revises: 20260826_06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260827_07"
down_revision: str | Sequence[str] | None = "20260826_06"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "spending_pools",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("current_amount", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.CheckConstraint("current_amount >= 0", name="ck_spending_pools_amount_non_negative"),
    )
    op.create_index("ix_spending_pools_user_id", "spending_pools", ["user_id"], unique=True)
    op.create_table(
        "planned_spending",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.CheckConstraint("amount > 0", name="ck_planned_spending_amount_positive"),
    )
    op.create_index("ix_planned_spending_user_id", "planned_spending", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_planned_spending_user_id", table_name="planned_spending")
    op.drop_table("planned_spending")
    op.drop_index("ix_spending_pools_user_id", table_name="spending_pools")
    op.drop_table("spending_pools")
