"""Add transaction directions and envelope opening balances.

Revision ID: 20260826_06
Revises: 20260826_05
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260826_06"
down_revision: str | Sequence[str] | None = "20260826_05"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("envelopes") as batch_op:
        batch_op.add_column(
            sa.Column("opening_amount", sa.Integer(), server_default="0", nullable=False)
        )
        batch_op.create_check_constraint(
            "ck_envelopes_opening_amount_non_negative",
            "opening_amount >= 0",
        )
    op.execute("UPDATE envelopes SET opening_amount = current_amount")

    with op.batch_alter_table("contributions") as batch_op:
        batch_op.add_column(
            sa.Column(
                "transaction_type",
                sa.String(length=32),
                server_default="contribution",
                nullable=False,
            )
        )
        batch_op.create_check_constraint(
            "ck_contributions_transaction_type_valid",
            "transaction_type IN ('contribution', 'withdrawal')",
        )


def downgrade() -> None:
    with op.batch_alter_table("contributions") as batch_op:
        batch_op.drop_constraint("ck_contributions_transaction_type_valid", type_="check")
        batch_op.drop_column("transaction_type")

    with op.batch_alter_table("envelopes") as batch_op:
        batch_op.drop_constraint("ck_envelopes_opening_amount_non_negative", type_="check")
        batch_op.drop_column("opening_amount")
