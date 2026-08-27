"""Add actual spending history records.

Revision ID: 20260827_09
Revises: 20260827_08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260827_09"
down_revision: str | Sequence[str] | None = "20260827_08"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "actual_spending",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("expense_name", sa.String(length=255), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("routine_id", sa.Integer(), nullable=True),
        sa.Column("planned_spending_id", sa.Integer(), nullable=True),
        sa.Column("spent_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["routine_id"], ["routine_spending.id"], ondelete="SET NULL"),
        sa.CheckConstraint("amount > 0", name="ck_actual_spending_amount_positive"),
        sa.CheckConstraint(
            "source_type IN ('routine', 'planned')",
            name="ck_actual_spending_source_type_valid",
        ),
    )
    op.create_index("ix_actual_spending_user_id", "actual_spending", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_actual_spending_user_id", table_name="actual_spending")
    op.drop_table("actual_spending")
