"""Add envelopes table.

Revision ID: 20260825_01
Revises: 20260825_00
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260825_01"
down_revision: str | Sequence[str] | None = "20260825_00"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "envelopes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("current_amount", sa.Integer(), server_default="0", nullable=False),
        sa.Column("target_amount", sa.Integer(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.CheckConstraint(
            "current_amount >= 0",
            name="ck_envelopes_current_amount_non_negative",
        ),
        sa.CheckConstraint("priority > 0", name="ck_envelopes_priority_positive"),
        sa.CheckConstraint("target_amount > 0", name="ck_envelopes_target_amount_positive"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_envelopes_user_id"), "envelopes", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_envelopes_user_id"), table_name="envelopes")
    op.drop_table("envelopes")
