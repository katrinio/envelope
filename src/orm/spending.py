from __future__ import annotations

from typing import TYPE_CHECKING, Self

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, select
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from src import database
from src.database import Base

if TYPE_CHECKING:
    from src.orm.user import User


class SpendingPool(Base):
    __tablename__ = "spending_pools"
    __table_args__ = (CheckConstraint("current_amount >= 0", name="ck_spending_pools_amount_non_negative"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    current_amount: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    user: Mapped[User] = relationship(back_populates="spending_pool")

    @validates("current_amount")
    def validate_current_amount(self, _key: str, value: int) -> int:
        if value < 0:
            raise ValueError("Available amount cannot be negative.")
        return value

    @classmethod
    def for_user(cls, user_id: int) -> Self:
        with database.SessionLocal.begin() as session:
            pool = session.scalar(select(cls).where(cls.user_id == user_id))
            if pool is None:
                pool = cls(user_id=user_id, current_amount=0)
                session.add(pool)
                session.flush()
            return pool

    def change_amount(self, amount: int, operation: str) -> Self:
        if amount <= 0:
            raise ValueError("Use an amount above 0.")
        with database.SessionLocal.begin() as session:
            pool = session.merge(self)
            new_amount = pool.current_amount + amount if operation == "increment" else pool.current_amount - amount
            if new_amount < 0:
                raise ValueError("Available amount cannot go below €0.")
            pool.current_amount = new_amount
            session.flush()
            return pool


class PlannedSpending(Base):
    __tablename__ = "planned_spending"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_planned_spending_amount_positive"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    user: Mapped[User] = relationship(back_populates="planned_spending")

    @validates("name")
    def validate_name(self, _key: str, value: str) -> str:
        normalized_name = value.strip()
        if not normalized_name:
            raise ValueError("Add a name.")
        if len(normalized_name) > 255:
            raise ValueError("Keep the name under 255 characters.")
        return normalized_name

    @validates("amount")
    def validate_amount(self, _key: str, value: int) -> int:
        if value <= 0:
            raise ValueError("Use an amount above 0.")
        return value

    @classmethod
    def for_user(cls, user_id: int) -> list[Self]:
        with database.SessionLocal() as session:
            return list(session.scalars(select(cls).where(cls.user_id == user_id).order_by(cls.id)).all())
