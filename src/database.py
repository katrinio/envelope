import os
from pathlib import Path
from typing import Any, Self

from sqlalchemy import create_engine, event, select
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, sessionmaker


def _enable_sqlite_foreign_keys(dbapi_connection: Any, _connection_record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def _create_engine(database_url: str) -> Engine:
    url = make_url(database_url)
    database_path = url.database

    if url.drivername.startswith("sqlite") and database_path and database_path != ":memory:":
        Path(database_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)

    connect_args = {"check_same_thread": False} if url.drivername.startswith("sqlite") else {}
    created_engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)
    if url.drivername.startswith("sqlite"):
        event.listen(created_engine, "connect", _enable_sqlite_foreign_keys)
    return created_engine


database_url = os.getenv("DATABASE_URL", "sqlite:///data/app.db")
engine = _create_engine(database_url)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    """Declarative base with a small synchronous Active Record API."""

    id: Mapped[int]

    @classmethod
    def create(cls, **values: Any) -> Self:
        record = cls(**values)
        return record.save()

    @classmethod
    def get(cls, record_id: int) -> Self | None:
        with SessionLocal() as session:
            return session.get(cls, record_id)

    @classmethod
    def all(cls) -> list[Self]:
        with SessionLocal() as session:
            return list(session.scalars(select(cls)).all())

    def save(self) -> Self:
        with SessionLocal.begin() as session:
            session.add(self)
            session.flush()
        return self

    def delete(self) -> None:
        with SessionLocal.begin() as session:
            record = session.merge(self)
            session.delete(record)


def init_database() -> None:
    # Import models before create_all so that they are registered in Base.metadata.
    from src.orm import contribution, envelope, spending, user  # noqa: F401

    Base.metadata.create_all(engine)


def session() -> Session:
    """Return a session for operations that need one shared transaction."""

    return SessionLocal()
