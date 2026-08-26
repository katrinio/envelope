import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, text


def _run_alembic(revision: str, database_url: str, project_root: Path) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", revision],
        cwd=project_root,
        env=os.environ | {"DATABASE_URL": database_url},
        check=True,
        capture_output=True,
        text=True,
    )


def test_existing_envelopes_become_regular_after_migration(tmp_path: Path) -> None:
    project_root = Path(__file__).parents[1]
    database_url = f"sqlite:///{tmp_path / 'migration.db'}"
    _run_alembic("20260825_02", database_url, project_root)

    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                'INSERT INTO users (id, "userId", username, salary) '
                "VALUES (1, 1, 'alice', 1500)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO envelopes "
                "(id, user_id, name, current_amount, target_amount, priority) "
                "VALUES (1, 1, 'Trip', 100, 1200, 1)"
            )
        )

    _run_alembic("head", database_url, project_root)

    with engine.connect() as connection:
        migrated_envelope = connection.execute(
            text("SELECT kind, target_amount FROM envelopes WHERE id = 1")
        ).one()

    assert migrated_envelope.kind == "regular"
    assert migrated_envelope.target_amount == 1_200
