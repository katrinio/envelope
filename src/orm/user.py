from __future__ import annotations

from typing import TYPE_CHECKING, Self

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base

if TYPE_CHECKING:
    from src.orm.envelope import Envelope


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    userId: Mapped[int] = mapped_column(Integer, unique=True)
    username: Mapped[str] = mapped_column(String(255), unique=True)
    salary: Mapped[int] = mapped_column(Integer)
    envelopes: Mapped[list[Envelope]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def update_salary(self, salary: int) -> Self:
        if salary <= 0:
            raise ValueError("Use an amount above 0.")
        self.salary = salary
        return self.save()
