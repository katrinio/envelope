from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, select
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from src import database
from src.database import Base

if TYPE_CHECKING:
    from src.orm.user import User


class Envelope(Base):
    __tablename__ = "envelopes"
    __table_args__ = (
        CheckConstraint("current_amount >= 0", name="ck_envelopes_current_amount_non_negative"),
        CheckConstraint("target_amount > 0", name="ck_envelopes_target_amount_positive"),
        CheckConstraint("priority > 0", name="ck_envelopes_priority_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    current_amount: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    target_amount: Mapped[int] = mapped_column(Integer)
    priority: Mapped[int] = mapped_column(Integer)

    user: Mapped[User] = relationship(back_populates="envelopes")

    @validates("current_amount")
    def validate_current_amount(self, _key: str, value: int) -> int:
        if value < 0:
            raise ValueError("current_amount cannot be negative")
        return value

    @validates("target_amount")
    def validate_target_amount(self, _key: str, value: int) -> int:
        if value <= 0:
            raise ValueError("target_amount must be greater than 0")
        return value

    @validates("priority")
    def validate_priority(self, _key: str, value: int) -> int:
        if value <= 0:
            raise ValueError("priority must be positive")
        return value

    @classmethod
    def for_user(cls, user_id: int) -> list[Envelope]:
        with database.SessionLocal() as session:
            query = select(cls).where(cls.user_id == user_id).order_by(cls.priority, cls.id)
            return list(session.scalars(query).all())
