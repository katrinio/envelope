from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any, Self

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, select, text
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from src import database
from src.database import Base
from src.envelope.service import calculate_financial_pillow_target

if TYPE_CHECKING:
    from src.orm.contribution import Contribution
    from src.orm.user import User


class EnvelopeKind(StrEnum):
    REGULAR = "regular"
    FINANCIAL_PILLOW = "financial_pillow"


class Envelope(Base):
    __tablename__ = "envelopes"
    __table_args__ = (
        CheckConstraint("current_amount >= 0", name="ck_envelopes_current_amount_non_negative"),
        CheckConstraint(
            "(kind = 'regular' AND target_amount > 0) OR "
            "(kind = 'financial_pillow' AND target_amount IS NULL)",
            name="ck_envelopes_target_amount_by_kind",
        ),
        CheckConstraint("priority > 0", name="ck_envelopes_priority_positive"),
        CheckConstraint("pillow_index > 0", name="ck_envelopes_pillow_index_positive"),
        CheckConstraint(
            "kind IN ('regular', 'financial_pillow')",
            name="ck_envelopes_kind_valid",
        ),
        Index(
            "uq_envelopes_financial_pillow_per_user",
            "user_id",
            unique=True,
            sqlite_where=text("kind = 'financial_pillow'"),
            postgresql_where=text("kind = 'financial_pillow'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    current_amount: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    _target_amount: Mapped[int | None] = mapped_column("target_amount", Integer, nullable=True)
    priority: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(32), default=EnvelopeKind.REGULAR, server_default="regular")
    pillow_index: Mapped[int] = mapped_column(Integer, default=2, server_default="2")

    user: Mapped[User] = relationship(back_populates="envelopes")
    contributions: Mapped[list[Contribution]] = relationship(
        back_populates="envelope",
        cascade="all, delete-orphan",
    )

    @validates("current_amount")
    def validate_current_amount(self, _key: str, value: int) -> int:
        if value < 0:
            raise ValueError("current_amount cannot be negative")
        return value

    @property
    def target_amount(self) -> int:
        if self.kind == EnvelopeKind.FINANCIAL_PILLOW:
            from src.orm.user import User

            user = User.get(self.user_id)
            if user is None:
                raise ValueError("A user is required for a financial pillow.")
            return calculate_financial_pillow_target(user.salary, self.pillow_index)
        if self._target_amount is None:
            raise ValueError("target_amount must be greater than 0")
        return self._target_amount

    @target_amount.setter
    def target_amount(self, value: int | None) -> None:
        self._target_amount = value

    @property
    def is_financial_pillow(self) -> bool:
        return self.kind == EnvelopeKind.FINANCIAL_PILLOW

    @validates("_target_amount")
    def validate_target_amount(self, _key: str, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("target_amount must be greater than 0")
        return value

    @validates("kind")
    def validate_kind(self, _key: str, value: str) -> str:
        try:
            return EnvelopeKind(value).value
        except ValueError:
            raise ValueError("Unknown envelope kind") from None

    @validates("priority")
    def validate_priority(self, _key: str, value: int) -> int:
        if value <= 0:
            raise ValueError("priority must be positive")
        return value

    @validates("pillow_index")
    def validate_pillow_index(self, _key: str, value: int) -> int:
        if value <= 0:
            raise ValueError("pillow_index must be positive")
        return value

    def update_configuration(self, name: str, target_amount: int | None = None) -> Self:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("Add a name.")
        if len(normalized_name) > 255:
            raise ValueError("Keep the name under 255 characters.")

        if self.is_financial_pillow:
            if target_amount is not None:
                raise ValueError("The financial pillow goal is calculated automatically.")
        elif target_amount is None or target_amount <= 0:
            raise ValueError("Use an amount above 0.")
        else:
            self._target_amount = target_amount

        self.name = normalized_name
        return self.save()

    @classmethod
    def create(cls, **values: Any) -> Self:
        kind = EnvelopeKind(values.pop("kind", EnvelopeKind.REGULAR))
        user_id = values.get("user_id")
        if not isinstance(user_id, int):
            raise ValueError("A user is required for an envelope.")

        from src.orm.user import User

        with database.SessionLocal.begin() as session:
            user = session.get(User, user_id)
            if user is None:
                raise ValueError("A user is required for an envelope.")

            target_amount = values.pop("target_amount", None)
            pillow_index = values.get("pillow_index", 2)
            if kind == EnvelopeKind.FINANCIAL_PILLOW:
                calculate_financial_pillow_target(user.salary, pillow_index)
                existing_pillow = session.scalar(
                    select(cls.id).where(
                        cls.user_id == user_id,
                        cls.kind == EnvelopeKind.FINANCIAL_PILLOW,
                    )
                )
                if existing_pillow is not None:
                    raise ValueError("You already have a financial pillow.")
                target_amount = None
            elif target_amount is None or target_amount <= 0:
                raise ValueError("target_amount must be greater than 0")

            record = cls(**values, kind=kind.value, _target_amount=target_amount)
            session.add(record)
            session.flush()
        return record

    @classmethod
    def for_user(cls, user_id: int) -> list[Envelope]:
        with database.SessionLocal() as session:
            query = select(cls).where(cls.user_id == user_id).order_by(cls.priority, cls.id)
            return list(session.scalars(query).all())
