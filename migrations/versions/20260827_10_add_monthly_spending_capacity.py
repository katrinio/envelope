"""Add monthly spending capacity state.

Revision ID: 20260827_10
Revises: 20260827_09
"""

from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision: str = "20260827_10"
down_revision: str | Sequence[str] | None = "20260827_09"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "monthly_spending_capacities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("month_key", sa.String(length=7), nullable=False),
        sa.Column("capacity_amount", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "capacity_amount >= 0",
            name="ck_monthly_spending_capacity_non_negative",
        ),
        sa.UniqueConstraint("user_id", "month_key", name="uq_monthly_spending_capacity_month"),
    )
    op.create_index(
        "ix_monthly_spending_capacities_user_id",
        "monthly_spending_capacities",
        ["user_id"],
    )
    current_month = datetime.now().strftime("%Y-%m")
    op.execute(
        f"INSERT INTO monthly_spending_capacities (user_id, month_key, capacity_amount) "
        f"SELECT user_id, '{current_month}', current_amount FROM spending_pools"
    )
    with op.batch_alter_table("actual_spending") as batch_op:
        batch_op.add_column(sa.Column("month_key", sa.String(length=7), nullable=True))
    op.execute("UPDATE actual_spending SET month_key = strftime('%Y-%m', spent_at)")
    with op.batch_alter_table("actual_spending") as batch_op:
        batch_op.alter_column("month_key", nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("actual_spending") as batch_op:
        batch_op.drop_column("month_key")
    op.drop_index("ix_monthly_spending_capacities_user_id", table_name="monthly_spending_capacities")
    op.drop_table("monthly_spending_capacities")
