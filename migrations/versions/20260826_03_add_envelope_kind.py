"""Add envelope kind.

Revision ID: 20260826_03
Revises: 20260825_02
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260826_03"
down_revision: str | Sequence[str] | None = "20260825_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("envelopes") as batch_op:
        batch_op.add_column(
            sa.Column("kind", sa.String(length=32), server_default="regular", nullable=False)
        )
        batch_op.drop_constraint("ck_envelopes_target_amount_positive", type_="check")
        batch_op.alter_column("target_amount", existing_type=sa.Integer(), nullable=True)
        batch_op.create_check_constraint(
            "ck_envelopes_target_amount_by_kind",
            "(kind = 'regular' AND target_amount > 0) OR "
            "(kind = 'financial_pillow' AND target_amount IS NULL)",
        )
        batch_op.create_check_constraint(
            "ck_envelopes_kind_valid",
            "kind IN ('regular', 'financial_pillow')",
        )

    op.create_index(
        "uq_envelopes_financial_pillow_per_user",
        "envelopes",
        ["user_id"],
        unique=True,
        sqlite_where=sa.text("kind = 'financial_pillow'"),
        postgresql_where=sa.text("kind = 'financial_pillow'"),
    )


def downgrade() -> None:
    op.execute(
        "UPDATE envelopes SET kind = 'regular', target_amount = "
        "(SELECT users.salary * 2 FROM users WHERE users.id = envelopes.user_id) "
        "WHERE kind = 'financial_pillow'"
    )
    op.drop_index("uq_envelopes_financial_pillow_per_user", table_name="envelopes")
    with op.batch_alter_table("envelopes") as batch_op:
        batch_op.drop_constraint("ck_envelopes_kind_valid", type_="check")
        batch_op.drop_constraint("ck_envelopes_target_amount_by_kind", type_="check")
        batch_op.alter_column("target_amount", existing_type=sa.Integer(), nullable=False)
        batch_op.create_check_constraint(
            "ck_envelopes_target_amount_positive",
            "target_amount > 0",
        )
        batch_op.drop_column("kind")
