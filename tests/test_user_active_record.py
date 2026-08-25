import subprocess
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src import database
from src.orm.user import User


def test_direct_user_import_registers_envelope_mapper() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from src.orm.user import User; "
                'User(userId=1, username="mapper-check", salary=1)'
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_user_active_record(tmp_path, monkeypatch) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    test_session = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", test_session)
    database.init_database()

    user = User.create(userId=1, username="alice", salary=100_000)

    assert user.id is not None
    assert User.get(user.id).username == "alice"
    assert [record.username for record in User.all()] == ["alice"]

    user.salary = 120_000
    user.save()
    assert User.get(user.id).salary == 120_000

    user.delete()
    assert User.get(user.id) is None
