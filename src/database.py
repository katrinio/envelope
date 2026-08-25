from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase

from src.config import settings

database_url = settings.database_url
url = make_url(database_url)
database_path = url.database
if url.drivername.startswith("sqlite") and database_path and database_path != ":memory:":
    Path(database_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    database_url,
    connect_args={"check_same_thread": False},
)


class Base(DeclarativeBase):
    pass
