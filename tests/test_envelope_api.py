from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src import database
from src.app import app
from src.orm.user import User


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    test_session = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", test_session)
    database.init_database()

    with TestClient(app) as test_client:
        yield test_client


def test_envelope_crud(client: TestClient) -> None:
    user = User.create(userId=1, username="alice", salary=100_000)

    create_response = client.post(
        f"/users/{user.id}/envelopes",
        json={"name": "Emergency fund", "target_amount": 50_000, "priority": 1},
    )
    assert create_response.status_code == 201
    envelope = create_response.json()
    assert envelope["current_amount"] == 0

    list_response = client.get(f"/users/{user.id}/envelopes")
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [envelope["id"]]
    with database.SessionLocal() as session:
        stored_user = session.get(User, user.id)
        assert stored_user is not None
        assert stored_user.envelopes[0].id == envelope["id"]

    get_response = client.get(f"/envelopes/{envelope['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["name"] == "Emergency fund"

    update_response = client.patch(
        f"/envelopes/{envelope['id']}/current-amount",
        json={"current_amount": 5_000},
    )
    assert update_response.status_code == 200
    assert update_response.json()["current_amount"] == 5_000

    delete_response = client.delete(f"/envelopes/{envelope['id']}")
    assert delete_response.status_code == 204

    get_deleted_response = client.get(f"/envelopes/{envelope['id']}")
    assert get_deleted_response.status_code == 404

    list_after_delete_response = client.get(f"/users/{user.id}/envelopes")
    assert list_after_delete_response.status_code == 200
    assert list_after_delete_response.json() == []


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "Invalid", "current_amount": -1, "target_amount": 100, "priority": 1},
        {"name": "Invalid", "current_amount": 0, "target_amount": 0, "priority": 1},
        {"name": "Invalid", "current_amount": 0, "target_amount": 100, "priority": 0},
    ],
)
def test_create_envelope_validation(client: TestClient, payload: dict[str, object]) -> None:
    user = User.create(userId=1, username="alice", salary=100_000)

    response = client.post(f"/users/{user.id}/envelopes", json=payload)

    assert response.status_code == 422


def test_create_envelope_for_missing_user(client: TestClient) -> None:
    response = client.post(
        "/users/999/envelopes",
        json={"name": "Emergency fund", "target_amount": 50_000, "priority": 1},
    )

    assert response.status_code == 404


def test_envelope_page_renders(client: TestClient) -> None:
    user = User.create(userId=1, username="alice", salary=100_000)

    response = client.get(f"/users/{user.id}/envelopes/page")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "alice" in response.text
    assert "100,000" in response.text


def test_envelope_page_shows_envelope_data(client: TestClient) -> None:
    user = User.create(userId=1, username="alice", salary=100_000)
    envelope = client.post(
        f"/users/{user.id}/envelopes",
        json={
            "name": "Home deposit",
            "current_amount": 25_000,
            "target_amount": 100_000,
            "priority": 1,
        },
    ).json()

    response = client.get(f"/users/{user.id}/envelopes/page")

    assert response.status_code == 200
    assert "Home deposit" in response.text
    assert "25,000" in response.text
    assert "100,000" in response.text
    assert f"amount-increment-{envelope['id']}" in response.text
    assert "€75,000 to go" in response.text
    assert "<details" in response.text
    assert '<details class="adjustment-control" open' not in response.text


def test_envelope_page_progress_calculation(client: TestClient) -> None:
    user = User.create(userId=1, username="alice", salary=100_000)
    client.post(
        f"/users/{user.id}/envelopes",
        json={"name": "Education", "current_amount": 250, "target_amount": 1_000, "priority": 1},
    )

    response = client.get(f"/users/{user.id}/envelopes/page")

    assert "25%" in response.text
    assert 'aria-valuenow="25"' in response.text
    assert 'data-progress="25"' in response.text
    assert response.text.count('class="progress-segment is-filled"') == 5


def test_envelope_page_empty_state(client: TestClient) -> None:
    user = User.create(userId=1, username="alice", salary=100_000)

    response = client.get(f"/users/{user.id}/envelopes/page")

    assert response.status_code == 200
    assert "No envelopes yet" in response.text
    assert 'aria-label="Savings envelopes"' not in response.text


def test_envelope_page_changes_current_amount(client: TestClient) -> None:
    user = User.create(userId=1, username="alice", salary=100_000)
    envelope = client.post(
        f"/users/{user.id}/envelopes",
        json={"name": "Emergency fund", "current_amount": 100, "target_amount": 1_000, "priority": 1},
    ).json()
    amount_url = f"/users/{user.id}/envelopes/{envelope['id']}/amount"

    increment_response = client.post(amount_url, data={"amount": 50, "operation": "increment"})
    assert increment_response.status_code == 200
    assert client.get(f"/envelopes/{envelope['id']}").json()["current_amount"] == 150

    decrement_response = client.post(amount_url, data={"amount": 25, "operation": "decrement"})
    assert decrement_response.status_code == 200
    assert client.get(f"/envelopes/{envelope['id']}").json()["current_amount"] == 125
