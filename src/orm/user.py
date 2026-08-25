from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    userId: Mapped[int] = mapped_column(Integer, unique=True)
    username: Mapped[str] = mapped_column(String(255), unique=True)
    salary: Mapped[int] = mapped_column(Integer)
