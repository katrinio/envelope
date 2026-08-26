from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Self

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, func, select
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from src import database
from src.database import Base

if TYPE_CHECKING:
    from src.orm.envelope import Envelope


class TransactionType(str):
    CONTRIBUTION = "contribution"
    WITHDRAWAL = "withdrawal"


class Contribution(Base):
    __tablename__ = "contributions"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_contributions_amount_positive"),
        CheckConstraint(
            "transaction_type IN ('contribution', 'withdrawal')",
            name="ck_contributions_transaction_type_valid",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    envelope_id: Mapped[int] = mapped_column(
        ForeignKey("envelopes.id", ondelete="CASCADE"),
        index=True,
    )
    amount: Mapped[int] = mapped_column(Integer)
    is_regular: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    transaction_type: Mapped[str] = mapped_column(
        "transaction_type",
        String(32),
        default=TransactionType.CONTRIBUTION,
        server_default=TransactionType.CONTRIBUTION,
    )
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

    @validates("transaction_type")
    def validate_transaction_type(self, _key: str, value: str) -> str:
        if value not in (TransactionType.CONTRIBUTION, TransactionType.WITHDRAWAL):
            raise ValueError("Unknown transaction type.")
        return value

    @property
    def is_withdrawal(self) -> bool:
        return self.transaction_type == TransactionType.WITHDRAWAL

    @property
    def display_sign(self) -> str:
        return "−" if self.is_withdrawal else "+"  # noqa: RUF001

    @property
    def display_label(self) -> str:
        if self.is_withdrawal:
            return "Withdrawal"
        return "Regular contribution" if self.is_regular else "One-time contribution"

    @classmethod
    def _recalculate_envelope_balance(
        cls,
        session: Any,
        envelope: Envelope,
        initialize_opening: bool = False,
    ) -> None:
        transactions = session.scalars(
            select(cls).where(cls.envelope_id == envelope.id)
        ).all()
        if (
            initialize_opening
            and not transactions
            and envelope.opening_amount == 0
            and envelope.current_amount != 0
        ):
            envelope.opening_amount = envelope.current_amount
        balance = envelope.opening_amount + sum(
            -transaction.amount if transaction.is_withdrawal else transaction.amount
            for transaction in transactions
        )
        if balance < 0:
            raise ValueError("Saved amount cannot go below €0.")
        envelope.current_amount = balance

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
            cls._recalculate_envelope_balance(session, envelope, initialize_opening=True)
            contribution = cls(
                envelope_id=envelope_id,
                amount=amount,
                is_regular=is_regular,
                transaction_type=TransactionType.CONTRIBUTION,
            )
            session.add(contribution)
            session.flush()
            cls._recalculate_envelope_balance(session, envelope)
        return contribution

    @classmethod
    def withdraw_from_envelope(cls, envelope_id: int, amount: int) -> Self:
        if amount <= 0:
            raise ValueError("Contribution amount must be positive.")

        from src.orm.envelope import Envelope

        with database.SessionLocal.begin() as session:
            envelope = session.get(Envelope, envelope_id)
            if envelope is None:
                raise ValueError("Envelope not found.")
            cls._recalculate_envelope_balance(session, envelope, initialize_opening=True)
            if envelope.current_amount - amount < 0:
                raise ValueError("Saved amount cannot go below €0.")
            transaction = cls(
                envelope_id=envelope_id,
                amount=amount,
                is_regular=False,
                transaction_type=TransactionType.WITHDRAWAL,
            )
            session.add(transaction)
            session.flush()
            cls._recalculate_envelope_balance(session, envelope)
        return transaction

    def update_transaction(
        self,
        amount: int,
        contributed_at: datetime,
        is_regular: bool = False,
    ) -> Self:
        if amount <= 0:
            raise ValueError("Contribution amount must be positive.")

        from src.orm.envelope import Envelope

        with database.SessionLocal.begin() as session:
            transaction = session.merge(self)
            envelope = session.get(Envelope, transaction.envelope_id)
            if envelope is None:
                raise ValueError("Envelope not found.")
            transaction.amount = amount
            transaction.contributed_at = contributed_at
            transaction.is_regular = (
                is_regular if transaction.transaction_type == TransactionType.CONTRIBUTION else False
            )
            type(self)._recalculate_envelope_balance(session, envelope)
            session.flush()
        return transaction

    def delete_transaction(self) -> None:
        from src.orm.envelope import Envelope

        with database.SessionLocal.begin() as session:
            transaction = session.merge(self)
            envelope = session.get(Envelope, transaction.envelope_id)
            if envelope is None:
                raise ValueError("Envelope not found.")
            session.delete(transaction)
            session.flush()
            type(self)._recalculate_envelope_balance(session, envelope)

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
    def newest_first_for_envelope(cls, envelope_id: int) -> list[Self]:
        with database.SessionLocal() as session:
            query = (
                select(cls)
                .where(cls.envelope_id == envelope_id)
                .order_by(cls.contributed_at.desc(), cls.id.desc())
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
