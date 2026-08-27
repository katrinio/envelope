"""Create the current application schema as a clean baseline.

Revision ID: 20260827_00
Revises: None
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260827_00"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("userId", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=False),
        sa.Column("salary", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("userId"),
        sa.UniqueConstraint("username"),
    )
    op.create_table(
        "envelopes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("current_amount", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("opening_amount", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("target_amount", sa.Integer(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False, server_default="regular"),
        sa.Column("pillow_index", sa.Integer(), nullable=False, server_default="2"),
        sa.CheckConstraint("current_amount >= 0", name="ck_envelopes_current_amount_non_negative"),
        sa.CheckConstraint("opening_amount >= 0", name="ck_envelopes_opening_amount_non_negative"),
        sa.CheckConstraint(
            "(kind = 'regular' AND target_amount > 0) OR "
            "(kind = 'financial_pillow' AND target_amount IS NULL)",
            name="ck_envelopes_target_amount_by_kind",
        ),
        sa.CheckConstraint("priority > 0", name="ck_envelopes_priority_positive"),
        sa.CheckConstraint("pillow_index > 0", name="ck_envelopes_pillow_index_positive"),
        sa.CheckConstraint("kind IN ('regular', 'financial_pillow')", name="ck_envelopes_kind_valid"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_envelopes_user_id", "envelopes", ["user_id"])
    op.create_index(
        "uq_envelopes_financial_pillow_per_user",
        "envelopes",
        ["user_id"],
        unique=True,
        sqlite_where=sa.text("kind = 'financial_pillow'"),
        postgresql_where=sa.text("kind = 'financial_pillow'"),
    )
    op.create_table(
        "contributions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("envelope_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("is_regular", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("transaction_type", sa.String(length=32), nullable=False, server_default="contribution"),
        sa.Column("contributed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("amount > 0", name="ck_contributions_amount_positive"),
        sa.CheckConstraint(
            "transaction_type IN ('contribution', 'withdrawal')",
            name="ck_contributions_transaction_type_valid",
        ),
        sa.ForeignKeyConstraint(["envelope_id"], ["envelopes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_contributions_envelope_id", "contributions", ["envelope_id"])
    op.create_table(
        "spending_pools",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("current_amount", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint("current_amount >= 0", name="ck_spending_pools_amount_non_negative"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_spending_pools_user_id", "spending_pools", ["user_id"], unique=True)
    op.create_table(
        "planned_spending",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_planned_spending_amount_positive"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_planned_spending_user_id", "planned_spending", ["user_id"])
    op.create_table(
        "routine_spending",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("default_amount", sa.Integer(), nullable=False),
        sa.CheckConstraint("default_amount > 0", name="ck_routine_spending_default_amount_positive"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_routine_spending_user_id", "routine_spending", ["user_id"])
    op.create_table(
        "routine_spending_selections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("routine_id", sa.Integer(), nullable=False),
        sa.Column("month_key", sa.String(length=7), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint("quantity > 0", name="ck_routine_spending_selections_quantity_positive"),
        sa.ForeignKeyConstraint(["routine_id"], ["routine_spending.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("routine_id", "month_key", name="uq_routine_spending_selection_month"),
    )
    op.create_index("ix_routine_spending_selections_routine_id", "routine_spending_selections", ["routine_id"])
    op.create_table(
        "actual_spending",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("expense_name", sa.String(length=255), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("month_key", sa.String(length=7), nullable=False),
        sa.Column("routine_id", sa.Integer(), nullable=True),
        sa.Column("planned_spending_id", sa.Integer(), nullable=True),
        sa.Column("spent_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("amount > 0", name="ck_actual_spending_amount_positive"),
        sa.CheckConstraint("source_type IN ('routine', 'planned')", name="ck_actual_spending_source_type_valid"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["routine_id"], ["routine_spending.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_actual_spending_user_id", "actual_spending", ["user_id"])
    op.create_table(
        "monthly_spending_capacities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("month_key", sa.String(length=7), nullable=False),
        sa.Column("capacity_amount", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint("capacity_amount >= 0", name="ck_monthly_spending_capacity_non_negative"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "month_key", name="uq_monthly_spending_capacity_month"),
    )
    op.create_index("ix_monthly_spending_capacities_user_id", "monthly_spending_capacities", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_monthly_spending_capacities_user_id", table_name="monthly_spending_capacities")
    op.drop_table("monthly_spending_capacities")
    op.drop_index("ix_actual_spending_user_id", table_name="actual_spending")
    op.drop_table("actual_spending")
    op.drop_index("ix_routine_spending_selections_routine_id", table_name="routine_spending_selections")
    op.drop_table("routine_spending_selections")
    op.drop_index("ix_routine_spending_user_id", table_name="routine_spending")
    op.drop_table("routine_spending")
    op.drop_index("ix_planned_spending_user_id", table_name="planned_spending")
    op.drop_table("planned_spending")
    op.drop_index("ix_spending_pools_user_id", table_name="spending_pools")
    op.drop_table("spending_pools")
    op.drop_index("ix_contributions_envelope_id", table_name="contributions")
    op.drop_table("contributions")
    op.drop_index("uq_envelopes_financial_pillow_per_user", table_name="envelopes")
    op.drop_index("ix_envelopes_user_id", table_name="envelopes")
    op.drop_table("envelopes")
    op.drop_table("users")
