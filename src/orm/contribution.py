from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Self

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, func, select
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from src import database
from src.database import Base

if TYPE_CHECKING:
    from src.orm.envelope import Envelope


class Contribution(Base):
    __tablename__ = "contributions"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_contributions_amount_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    envelope_id: Mapped[int] = mapped_column(
        ForeignKey("envelopes.id", ondelete="CASCADE"),
        index=True,
    )
    amount: Mapped[int] = mapped_column(Integer)
    is_regular: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    contributed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    envelope: Mapped[Envelope] = relationship(back_populates="contributions")

    @validates("amount")
    def validate_amount(self, _key: str, value: int) -> int:
        if value <= 0:
            raise ValueError("Contribution amount must be positive.")
        return value

    @classmethod
    def add_to_envelope(
        cls,
        envelope_id: int,
        amount: int,
        is_regular: bool = True,
    ) -> Self:
        if amount <= 0:
            raise ValueError("Contribution amount must be positive.")

        from src.orm.envelope import Envelope

        with database.SessionLocal.begin() as session:
            envelope = session.get(Envelope, envelope_id)
            if envelope is None:
                raise ValueError("Envelope not found.")
            envelope.current_amount += amount
            contribution = cls(
                envelope_id=envelope_id,
                amount=amount,
                is_regular=is_regular,
            )
            session.add(contribution)
            session.flush()
        return contribution

    @classmethod
    def for_envelope(cls, envelope_id: int) -> list[Self]:
        with database.SessionLocal() as session:
            query = (
                select(cls)
                .where(cls.envelope_id == envelope_id)
                .order_by(cls.contributed_at, cls.id)
            )
            return list(session.scalars(query).all())

    @classmethod
    def regular_for_user(cls, user_id: int) -> list[Self]:
        from src.orm.envelope import Envelope

        with database.SessionLocal() as session:
            query = (
                select(cls)
                .join(Envelope, cls.envelope_id == Envelope.id)
                .where(
                    Envelope.user_id == user_id,
                    cls.is_regular.is_(True),
                )
                .order_by(cls.contributed_at, cls.id)
            )
            return list(session.scalars(query).all())
