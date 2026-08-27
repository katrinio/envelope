from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Self, cast

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint, func, select
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from src import database
from src.database import Base

SIGNIFICANT_SPENDING_THRESHOLD = 5_000

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
            return cast(Self, pool)

    def change_amount(self, amount: int, operation: str) -> Self:
        return cast(Self, change_monthly_pool(self.user_id, amount, operation, current_month_key()))


class MonthlySpendingCapacity(Base):
    __tablename__ = "monthly_spending_capacities"
    __table_args__ = (
        CheckConstraint("capacity_amount >= 0", name="ck_monthly_spending_capacity_non_negative"),
        UniqueConstraint("user_id", "month_key", name="uq_monthly_spending_capacity_month"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    month_key: Mapped[str] = mapped_column(String(7), nullable=False)
    capacity_amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    @validates("capacity_amount")
    def validate_capacity_amount(self, _key: str, value: int) -> int:
        if value < 0:
            raise ValueError("Monthly capacity cannot be negative.")
        return value

    @classmethod
    def for_user_month(cls, user_id: int, month_key: str) -> Self:
        with database.SessionLocal.begin() as session:
            capacity = session.scalar(
                select(cls).where(cls.user_id == user_id, cls.month_key == month_key)
            )
            if capacity is None:
                capacity = cls(user_id=user_id, month_key=month_key, capacity_amount=0)
                session.add(capacity)
                session.flush()
            return capacity


@dataclass(frozen=True)
class MonthlyMoneyState:
    capacity: int
    free: int
    planned: int
    spent: int

    @property
    def free_percentage(self) -> float:
        return self._percentage(self.free)

    @property
    def planned_percentage(self) -> float:
        return self._percentage(self.planned)

    @property
    def spent_percentage(self) -> float:
        return self._percentage(self.spent)

    def _percentage(self, amount: int) -> float:
        if self.capacity <= 0:
            return 0
        return amount / self.capacity * 100


def current_month_key() -> str:
    return datetime.now().strftime("%Y-%m")


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
    month_key: Mapped[str] = mapped_column(String(7), nullable=False)
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

    @classmethod
    def significant_planned_for_months(
        cls,
        user_id: int,
        month_keys: list[str],
        threshold: int = SIGNIFICANT_SPENDING_THRESHOLD,
    ) -> list[Self]:
        if not month_keys:
            return []
        with database.SessionLocal() as session:
            return list(
                session.scalars(
                    select(cls)
                    .where(
                        cls.user_id == user_id,
                        cls.source_type == SpendingSourceType.PLANNED,
                        cls.month_key.in_(month_keys),
                        cls.amount >= threshold,
                    )
                    .order_by(cls.spent_at.desc(), cls.id.desc())
                ).all()
            )


def planned_amount_for_month(user_id: int, month_key: str) -> int:
    routines = RoutineSpending.for_user(user_id)
    selections = RoutineSpendingSelection.for_month([routine.id for routine in routines], month_key)
    return sum(
        routine.default_amount * selections[routine.id].quantity
        for routine in routines
        if routine.id in selections
    )


def spent_amount_for_month(user_id: int, month_key: str) -> int:
    with database.SessionLocal() as session:
        return sum(
            session.scalars(
                select(ActualSpending.amount).where(
                    ActualSpending.user_id == user_id,
                    ActualSpending.month_key == month_key,
                )
            ).all()
        )


def monthly_money_state(user_id: int, month_key: str) -> MonthlyMoneyState:
    capacity = MonthlySpendingCapacity.for_user_month(user_id, month_key).capacity_amount
    planned = planned_amount_for_month(user_id, month_key)
    spent = spent_amount_for_month(user_id, month_key)
    return MonthlyMoneyState(
        capacity=capacity,
        free=max(capacity - planned - spent, 0),
        planned=planned,
        spent=spent,
    )


def change_monthly_pool(user_id: int, amount: int, operation: str, month_key: str) -> SpendingPool:
    if amount <= 0:
        raise ValueError("Use an amount above 0.")
    with database.SessionLocal.begin() as session:
        pool = session.scalar(select(SpendingPool).where(SpendingPool.user_id == user_id))
        if pool is None:
            pool = SpendingPool(user_id=user_id, current_amount=0)
            session.add(pool)
            session.flush()
        capacity = session.scalar(
            select(MonthlySpendingCapacity).where(
                MonthlySpendingCapacity.user_id == user_id,
                MonthlySpendingCapacity.month_key == month_key,
            )
        )
        if capacity is None:
            capacity = MonthlySpendingCapacity(user_id=user_id, month_key=month_key, capacity_amount=0)
            session.add(capacity)
            session.flush()
        if operation == "increment":
            pool.current_amount += amount
            capacity.capacity_amount += amount
            session.flush()
            return pool

        spent = sum(
            session.scalars(
                select(ActualSpending.amount).where(
                    ActualSpending.user_id == user_id,
                    ActualSpending.month_key == month_key,
                )
            ).all()
        )
        planned = planned_amount_for_month(user_id, month_key)
        new_capacity = capacity.capacity_amount - amount
        new_pool_amount = pool.current_amount - amount
        if new_pool_amount < 0 or new_capacity < spent + planned:
            raise ValueError("Not enough free money.")
        pool.current_amount = new_pool_amount
        capacity.capacity_amount = new_capacity
        session.flush()
        return pool


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
        spent = sum(
            session.scalars(
                select(ActualSpending.amount).where(
                    ActualSpending.user_id == user_id,
                    ActualSpending.month_key == month_key,
                )
            ).all()
        )
        capacity = session.scalar(
            select(MonthlySpendingCapacity.capacity_amount).where(
                MonthlySpendingCapacity.user_id == user_id,
                MonthlySpendingCapacity.month_key == month_key,
            )
        ) or 0
        if pool.current_amount < amount or capacity < spent + amount:
            raise ValueError("Not enough available money.")
        pool.current_amount -= amount
        transaction = ActualSpending(
            user_id=user_id,
            expense_name=routine.name,
            amount=amount,
            source_type=SpendingSourceType.ROUTINE,
            month_key=month_key,
            routine_id=routine.id,
        )
        session.add(transaction)
        session.delete(selection)
        session.flush()
        return transaction


def spend_planned_item(user_id: int, item_id: int, month_key: str) -> ActualSpending:
    with database.SessionLocal.begin() as session:
        pool = session.scalar(select(SpendingPool).where(SpendingPool.user_id == user_id))
        item = session.get(PlannedSpending, item_id)
        if pool is None:
            pool = SpendingPool(user_id=user_id, current_amount=0)
            session.add(pool)
            session.flush()
        if item is None or item.user_id != user_id:
            raise ValueError("Planned spending not found.")
        capacity = session.scalar(
            select(MonthlySpendingCapacity.capacity_amount).where(
                MonthlySpendingCapacity.user_id == user_id,
                MonthlySpendingCapacity.month_key == month_key,
            )
        ) or 0
        spent = sum(
            session.scalars(
                select(ActualSpending.amount).where(
                    ActualSpending.user_id == user_id,
                    ActualSpending.month_key == month_key,
                )
            ).all()
        )
        planned = planned_amount_for_month(user_id, month_key)
        if pool.current_amount < item.amount or capacity - spent - planned < item.amount:
            raise ValueError("Not enough available money.")
        pool.current_amount -= item.amount
        transaction = ActualSpending(
            user_id=user_id,
            expense_name=item.name,
            amount=item.amount,
            source_type=SpendingSourceType.PLANNED,
            month_key=month_key,
            planned_spending_id=item.id,
        )
        session.add(transaction)
        session.delete(item)
        session.flush()
        return transaction
