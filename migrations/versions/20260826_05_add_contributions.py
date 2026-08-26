"""Add envelope contributions.

Revision ID: 20260826_05
Revises: 20260826_04
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260826_05"
down_revision: str | Sequence[str] | None = "20260826_04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "contributions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("envelope_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("is_regular", sa.Boolean(), server_default="1", nullable=False),
        sa.Column(
            "contributed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("amount > 0", name="ck_contributions_amount_positive"),
        sa.ForeignKeyConstraint(["envelope_id"], ["envelopes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_contributions_envelope_id"),
        "contributions",
        ["envelope_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_contributions_envelope_id"), table_name="contributions")
    op.drop_table("contributions")
