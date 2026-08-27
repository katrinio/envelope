from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Self

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint, func, select
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
                raise ValueError("Available amount cannot go below 0 RSD.")
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


class RoutineSpending(Base):
    __tablename__ = "routine_spending"
    __table_args__ = (CheckConstraint("default_amount > 0", name="ck_routine_spending_default_amount_positive"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    default_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    user: Mapped[User] = relationship(back_populates="routine_spending")
    monthly_selections: Mapped[list[RoutineSpendingSelection]] = relationship(
        back_populates="routine", cascade="all, delete-orphan"
    )

    @validates("name")
    def validate_name(self, _key: str, value: str) -> str:
        normalized_name = value.strip()
        if not normalized_name:
            raise ValueError("Add a name.")
        if len(normalized_name) > 255:
            raise ValueError("Keep the name under 255 characters.")
        return normalized_name

    @validates("default_amount")
    def validate_default_amount(self, _key: str, value: int) -> int:
        if value <= 0:
            raise ValueError("Use an amount above 0.")
        return value

    @classmethod
    def for_user(cls, user_id: int) -> list[Self]:
        with database.SessionLocal() as session:
            return list(session.scalars(select(cls).where(cls.user_id == user_id).order_by(cls.id)).all())


class RoutineSpendingSelection(Base):
    __tablename__ = "routine_spending_selections"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_routine_spending_selections_quantity_positive"),
        UniqueConstraint("routine_id", "month_key", name="uq_routine_spending_selection_month"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    routine_id: Mapped[int] = mapped_column(ForeignKey("routine_spending.id", ondelete="CASCADE"), index=True)
    month_key: Mapped[str] = mapped_column(String(7), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    routine: Mapped[RoutineSpending] = relationship(back_populates="monthly_selections")

    @validates("quantity")
    def validate_quantity(self, _key: str, value: int) -> int:
        if value <= 0:
            raise ValueError("Use a quantity above 0.")
        return value

    @classmethod
    def for_month(cls, routine_ids: list[int], month_key: str) -> dict[int, Self]:
        if not routine_ids:
            return {}
        with database.SessionLocal() as session:
            selections = session.scalars(
                select(cls).where(cls.routine_id.in_(routine_ids), cls.month_key == month_key)
            ).all()
            return {selection.routine_id: selection for selection in selections}

    @classmethod
    def set_for_month(cls, routine_id: int, month_key: str, quantity: int | None) -> None:
        with database.SessionLocal.begin() as session:
            selection = session.scalar(
                select(cls).where(cls.routine_id == routine_id, cls.month_key == month_key)
            )
            if quantity is None:
                if selection is not None:
                    session.delete(selection)
                return
            if quantity <= 0:
                raise ValueError("Use a quantity above 0.")
            if selection is None:
                session.add(cls(routine_id=routine_id, month_key=month_key, quantity=quantity))
            else:
                selection.quantity = quantity


class SpendingSourceType(str):
    ROUTINE = "routine"
    PLANNED = "planned"


class ActualSpending(Base):
    __tablename__ = "actual_spending"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_actual_spending_amount_positive"),
        CheckConstraint(
            "source_type IN ('routine', 'planned')",
            name="ck_actual_spending_source_type_valid",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expense_name: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    routine_id: Mapped[int | None] = mapped_column(
        ForeignKey("routine_spending.id", ondelete="SET NULL"),
        nullable=True,
    )
    planned_spending_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    spent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    @validates("expense_name")
    def validate_expense_name(self, _key: str, value: str) -> str:
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

    @validates("source_type")
    def validate_source_type(self, _key: str, value: str) -> str:
        if value not in (SpendingSourceType.ROUTINE, SpendingSourceType.PLANNED):
            raise ValueError("Unknown spending source.")
        return value

    @classmethod
    def for_user(cls, user_id: int) -> list[Self]:
        with database.SessionLocal() as session:
            return list(
                session.scalars(
                    select(cls).where(cls.user_id == user_id).order_by(cls.spent_at.desc(), cls.id.desc())
                ).all()
            )


def spend_routine_for_month(user_id: int, routine_id: int, month_key: str) -> ActualSpending:
    with database.SessionLocal.begin() as session:
        pool = session.scalar(select(SpendingPool).where(SpendingPool.user_id == user_id))
        routine = session.get(RoutineSpending, routine_id)
        if pool is None:
            pool = SpendingPool(user_id=user_id, current_amount=0)
            session.add(pool)
            session.flush()
        if routine is None or routine.user_id != user_id:
            raise ValueError("Routine spending not found.")
        selection = session.scalar(
            select(RoutineSpendingSelection).where(
                RoutineSpendingSelection.routine_id == routine_id,
                RoutineSpendingSelection.month_key == month_key,
            )
        )
        if selection is None:
            raise ValueError("Plan this routine expense before spending it.")
        amount = routine.default_amount * selection.quantity
        if pool.current_amount < amount:
            raise ValueError("Not enough available money.")
        pool.current_amount -= amount
        transaction = ActualSpending(
            user_id=user_id,
            expense_name=routine.name,
            amount=amount,
            source_type=SpendingSourceType.ROUTINE,
            routine_id=routine.id,
        )
        session.add(transaction)
        session.delete(selection)
        session.flush()
        return transaction


def spend_planned_item(user_id: int, item_id: int) -> ActualSpending:
    with database.SessionLocal.begin() as session:
        pool = session.scalar(select(SpendingPool).where(SpendingPool.user_id == user_id))
        item = session.get(PlannedSpending, item_id)
        if pool is None:
            pool = SpendingPool(user_id=user_id, current_amount=0)
            session.add(pool)
            session.flush()
        if item is None or item.user_id != user_id:
            raise ValueError("Planned spending not found.")
        if pool.current_amount < item.amount:
            raise ValueError("Not enough available money.")
        pool.current_amount -= item.amount
        transaction = ActualSpending(
            user_id=user_id,
            expense_name=item.name,
            amount=item.amount,
            source_type=SpendingSourceType.PLANNED,
            planned_spending_id=item.id,
        )
        session.add(transaction)
        session.delete(item)
        session.flush()
        return transaction
