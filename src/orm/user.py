
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Sequence

from sqlalchemy import Date, DateTime, String, select, or_
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship
from sqlalchemy.sql.functions import func

from src.database import Base, engine
from src.orm.milestone_tags import milestone_tags
from src.features.milestones.helpers import slug_from_title, slug_with_suffix




class User(Base):
    __tablename__ = "milestones"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    description: Mapped[str] = mapped_column(String, server_default="")
    happened_at: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    tags: Mapped[list[Tag]] = relationship(
        "Tag",
        secondary=milestone_tags,
        back_populates="milestones",
        lazy="selectin",
    )