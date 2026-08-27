"""Add routine spending templates and monthly selections.

Revision ID: 20260827_08
Revises: 20260827_07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260827_08"
down_revision: str | Sequence[str] | None = "20260827_07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "routine_spending",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("default_amount", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "default_amount > 0",
            name="ck_routine_spending_default_amount_positive",
        ),
    )
    op.create_index("ix_routine_spending_user_id", "routine_spending", ["user_id"])
    op.create_table(
        "routine_spending_selections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("routine_id", sa.Integer(), nullable=False),
        sa.Column("month_key", sa.String(length=7), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["routine_id"], ["routine_spending.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "quantity > 0",
            name="ck_routine_spending_selections_quantity_positive",
        ),
        sa.UniqueConstraint("routine_id", "month_key", name="uq_routine_spending_selection_month"),
    )
    op.create_index(
        "ix_routine_spending_selections_routine_id",
        "routine_spending_selections",
        ["routine_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_routine_spending_selections_routine_id", table_name="routine_spending_selections")
    op.drop_table("routine_spending_selections")
    op.drop_index("ix_routine_spending_user_id", table_name="routine_spending")
    op.drop_table("routine_spending")
