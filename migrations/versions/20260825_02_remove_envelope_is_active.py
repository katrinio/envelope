"""Remove envelopes is_active column.

Revision ID: 20260825_02
Revises: 20260825_01
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260825_02"
down_revision: str | Sequence[str] | None = "20260825_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("envelopes", "is_active")


def downgrade() -> None:
    op.add_column(
        "envelopes",
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
