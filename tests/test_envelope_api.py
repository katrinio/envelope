from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src import database
from src.app import app
from src.orm.envelope import Envelope
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
    assert envelope["kind"] == "regular"

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
    assert response.text.count('class="progress-segment is-filled"') == 2


def test_creation_tile_is_rendered_without_envelopes(client: TestClient) -> None:
    user = User.create(userId=1, username="alice", salary=100_000)

    response = client.get(f"/users/{user.id}/envelopes/page")

    assert response.status_code == 200
    assert 'class="creation-device"' in response.text
    assert "New envelope" in response.text
    assert 'class="envelope-device"' not in response.text


def test_creation_tile_is_rendered_after_existing_envelopes(client: TestClient) -> None:
    user = User.create(userId=1, username="alice", salary=100_000)
    Envelope.create(
        user_id=user.id,
        name="Trip",
        target_amount=1_200,
        priority=1,
    )

    response = client.get(f"/users/{user.id}/envelopes/page")

    assert response.status_code == 200
    assert response.text.index("Trip") < response.text.index("New envelope")


def test_valid_envelope_is_created_and_displayed(client: TestClient) -> None:
    user = User.create(userId=1, username="alice", salary=100_000)

    response = client.post(
        f"/users/{user.id}/envelopes/create",
        data={"name": "  Trip  ", "target_amount": "1200"},
    )

    assert response.status_code == 200
    assert "Trip" in response.text
    assert "€1,200" in response.text
    envelopes = Envelope.for_user(user.id)
    assert len(envelopes) == 1
    assert envelopes[0].name == "Trip"
    assert envelopes[0].target_amount == 1_200
    assert envelopes[0].priority == 1
    assert response.text.index("Trip") < response.text.index("New envelope")


@pytest.mark.parametrize("name", ["", "   "])
def test_envelope_creation_requires_name(client: TestClient, name: str) -> None:
    user = User.create(userId=1, username="alice", salary=100_000)

    response = client.post(
        f"/users/{user.id}/envelopes/create",
        data={"name": name, "target_amount": "1200"},
    )

    assert response.status_code == 422
    assert "Add a name." in response.text
    assert '<details class="creation-device" open>' in response.text
    assert Envelope.for_user(user.id) == []


@pytest.mark.parametrize(
    ("target_amount", "message"),
    [("0", "Use an amount above 0."), ("-1", "Use an amount above 0."), ("abc", "Enter a whole amount.")],
)
def test_envelope_creation_validates_target_amount(
    client: TestClient,
    target_amount: str,
    message: str,
) -> None:
    user = User.create(userId=1, username="alice", salary=100_000)

    response = client.post(
        f"/users/{user.id}/envelopes/create",
        data={"name": "Trip", "target_amount": target_amount},
    )

    assert response.status_code == 422
    assert message in response.text
    assert Envelope.for_user(user.id) == []


def test_envelope_creation_can_be_cancelled(client: TestClient) -> None:
    user = User.create(userId=1, username="alice", salary=100_000)
    page_url = f"/users/{user.id}/envelopes/page"
    invalid_response = client.post(
        f"/users/{user.id}/envelopes/create",
        data={"name": "Trip", "target_amount": "0"},
    )
    assert 'value="Trip"' in invalid_response.text
    assert f'href="http://testserver{page_url}"' in invalid_response.text

    cancel_response = client.get(page_url)

    assert cancel_response.status_code == 200
    assert '<details class="creation-device" open>' not in cancel_response.text
    assert 'value="Trip"' not in cancel_response.text
    assert Envelope.for_user(user.id) == []


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


def test_financial_pillow_uses_current_salary_and_ignores_supplied_target(
    client: TestClient,
) -> None:
    user = User.create(userId=1, username="alice", salary=1_500)

    response = client.post(
        f"/users/{user.id}/envelopes",
        json={
            "name": "Rainy days",
            "target_amount": 1,
            "priority": 1,
            "kind": "financial_pillow",
        },
    )

    assert response.status_code == 201
    envelope_data = response.json()
    assert envelope_data["name"] == "Rainy days"
    assert envelope_data["kind"] == "financial_pillow"
    assert envelope_data["target_amount"] == 3_000
    with database.SessionLocal() as session:
        stored_envelope = session.get(Envelope, envelope_data["id"])
        assert stored_envelope is not None
        assert stored_envelope._target_amount is None

    user.salary = 2_000
    user.save()

    updated_response = client.get(f"/envelopes/{envelope_data['id']}")
    assert updated_response.status_code == 200
    assert updated_response.json()["target_amount"] == 4_000
    updated_page = client.get(f"/users/{user.id}/envelopes/page")
    assert "€4,000" in updated_page.text


def test_only_one_financial_pillow_is_allowed_per_user(client: TestClient) -> None:
    user = User.create(userId=1, username="alice", salary=1_500)
    payload = {
        "name": "Reserve",
        "priority": 1,
        "kind": "financial_pillow",
    }

    first_response = client.post(f"/users/{user.id}/envelopes", json=payload)
    second_response = client.post(
        f"/users/{user.id}/envelopes",
        json={**payload, "name": "Backup", "priority": 2},
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 422
    assert second_response.json()["detail"] == "You already have a financial pillow."
    assert len(Envelope.for_user(user.id)) == 1


def test_different_users_can_have_financial_pillows(client: TestClient) -> None:
    alice = User.create(userId=1, username="alice", salary=1_500)
    bob = User.create(userId=2, username="bob", salary=2_000)

    for user in (alice, bob):
        response = client.post(
            f"/users/{user.id}/envelopes",
            json={
                "name": "Reserve",
                "priority": 1,
                "kind": "financial_pillow",
            },
        )
        assert response.status_code == 201

    assert Envelope.for_user(alice.id)[0].target_amount == 3_000
    assert Envelope.for_user(bob.id)[0].target_amount == 4_000


def test_financial_pillow_requires_positive_salary(client: TestClient) -> None:
    user = User.create(userId=1, username="alice", salary=0)

    response = client.post(
        f"/users/{user.id}/envelopes",
        json={"name": "Reserve", "priority": 1, "kind": "financial_pillow"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "A positive salary is needed for a financial pillow."


def test_financial_pillow_creation_ui_and_calculated_goal(client: TestClient) -> None:
    user = User.create(userId=1, username="alice", salary=1_500)

    initial_page = client.get(f"/users/{user.id}/envelopes/page")
    assert 'id="financial-pillow"' in initial_page.text
    assert "Financial pillow" in initial_page.text
    assert 'class="creation-field regular-goal"' in initial_page.text
    assert 'class="creation-field pillow-goal"' in initial_page.text
    assert "€3,000" in initial_page.text
    assert f"2 {chr(215)} monthly salary" in initial_page.text
    assert "A reserve for unexpected expenses." in initial_page.text

    create_response = client.post(
        f"/users/{user.id}/envelopes/create",
        data={
            "name": "Whatever name",
            "target_amount": "1",
            "financial_pillow": "financial_pillow",
        },
    )

    assert create_response.status_code == 200
    assert "Whatever name" in create_response.text
    assert "€3,000" in create_response.text
    envelope = Envelope.for_user(user.id)[0]
    assert envelope.is_financial_pillow
    assert envelope.target_amount == 3_000


def test_financial_pillow_checkbox_switches_goal_presentation(client: TestClient) -> None:
    user = User.create(userId=1, username="alice", salary=1_500)

    response = client.get(f"/users/{user.id}/envelopes/page")
    stylesheet = Path("src/static/envelope.css").read_text()

    assert response.status_code == 200
    assert 'class="pillow-toggle"' in response.text
    assert ".creation-form:has(.pillow-toggle:checked) .regular-goal" in stylesheet
    assert ".creation-form:has(.pillow-toggle:checked) .pillow-goal" in stylesheet


def test_financial_pillow_option_is_disabled_after_creation(client: TestClient) -> None:
    user = User.create(userId=1, username="alice", salary=1_500)
    Envelope.create(
        user_id=user.id,
        name="Reserve",
        priority=1,
        kind="financial_pillow",
    )

    response = client.get(f"/users/{user.id}/envelopes/page")

    assert response.status_code == 200
    checkbox = response.text.split('id="financial-pillow"', maxsplit=1)[1].split(">", maxsplit=1)[0]
    assert "disabled" in checkbox
    assert "You already have a financial pillow." in response.text


def test_financial_pillow_progress_uses_calculated_target(client: TestClient) -> None:
    user = User.create(userId=1, username="alice", salary=1_000)
    Envelope.create(
        user_id=user.id,
        name="Safe place",
        current_amount=1_000,
        priority=1,
        kind="financial_pillow",
    )

    response = client.get(f"/users/{user.id}/envelopes/page")

    assert response.status_code == 200
    assert "50%" in response.text
    assert 'aria-valuenow="50"' in response.text
    assert response.text.count('class="progress-segment is-filled"') == 5
    assert "€1,000 to go" in response.text
    assert f"2 {chr(215)} monthly salary" in response.text


def test_financial_pillow_form_keeps_selection_after_validation_error(
    client: TestClient,
) -> None:
    user = User.create(userId=1, username="alice", salary=1_500)

    response = client.post(
        f"/users/{user.id}/envelopes/create",
        data={"name": "   ", "financial_pillow": "financial_pillow"},
    )

    assert response.status_code == 422
    assert "Add a name." in response.text
    checkbox = response.text.split('id="financial-pillow"', maxsplit=1)[1].split(">", maxsplit=1)[0]
    assert "checked" in checkbox
    assert "€3,000" in response.text


def test_envelope_edit_menu_is_rendered(client: TestClient) -> None:
    user = User.create(userId=1, username="alice", salary=1_500)
    envelope = Envelope.create(
        user_id=user.id,
        name="Trip",
        target_amount=1_200,
        priority=1,
    )

    response = client.get(f"/users/{user.id}/envelopes/page")

    assert response.status_code == 200
    assert 'class="device-menu"' in response.text
    assert "•••" in response.text
    assert "Edit" in response.text
    assert "Delete" in response.text
    assert f"?edit_envelope_id={envelope.id}" in response.text


def test_regular_envelope_name_can_be_updated(client: TestClient) -> None:
    user = User.create(userId=1, username="alice", salary=1_500)
    envelope = Envelope.create(
        user_id=user.id,
        name="Trip",
        current_amount=300,
        target_amount=1_200,
        priority=1,
    )

    response = client.patch(
        f"/envelopes/{envelope.id}",
        json={"name": "  New trip  ", "target_amount": 1_200},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "New trip"
    assert response.json()["current_amount"] == 300
    assert response.json()["kind"] == "regular"


def test_regular_envelope_goal_can_be_updated(client: TestClient) -> None:
    user = User.create(userId=1, username="alice", salary=1_500)
    envelope = Envelope.create(
        user_id=user.id,
        name="Trip",
        current_amount=300,
        target_amount=1_200,
        priority=1,
    )

    response = client.patch(
        f"/envelopes/{envelope.id}",
        json={"name": "Trip", "target_amount": 2_000},
    )

    assert response.status_code == 200
    assert response.json()["target_amount"] == 2_000
    assert response.json()["current_amount"] == 300


@pytest.mark.parametrize("name", ["", "   "])
def test_envelope_edit_rejects_blank_name(client: TestClient, name: str) -> None:
    user = User.create(userId=1, username="alice", salary=1_500)
    envelope = Envelope.create(
        user_id=user.id,
        name="Trip",
        target_amount=1_200,
        priority=1,
    )

    response = client.patch(
        f"/envelopes/{envelope.id}",
        json={"name": name, "target_amount": 1_200},
    )

    assert response.status_code == 422
    assert Envelope.get(envelope.id).name == "Trip"  # type: ignore[union-attr]


@pytest.mark.parametrize("target_amount", [0, -1])
def test_regular_envelope_edit_rejects_non_positive_goal(
    client: TestClient,
    target_amount: int,
) -> None:
    user = User.create(userId=1, username="alice", salary=1_500)
    envelope = Envelope.create(
        user_id=user.id,
        name="Trip",
        target_amount=1_200,
        priority=1,
    )

    response = client.patch(
        f"/envelopes/{envelope.id}",
        json={"name": "Trip", "target_amount": target_amount},
    )

    assert response.status_code == 422
    assert Envelope.get(envelope.id).target_amount == 1_200  # type: ignore[union-attr]


def test_envelope_edit_cancel_does_not_persist_changes(client: TestClient) -> None:
    user = User.create(userId=1, username="alice", salary=1_500)
    envelope = Envelope.create(
        user_id=user.id,
        name="Trip",
        target_amount=1_200,
        priority=1,
    )
    page_url = f"/users/{user.id}/envelopes/page"

    edit_response = client.get(f"{page_url}?edit_envelope_id={envelope.id}")
    cancel_response = client.get(page_url)

    assert edit_response.status_code == 200
    assert "Edit envelope" in edit_response.text
    assert f'href="http://testserver{page_url}"' in edit_response.text
    assert cancel_response.status_code == 200
    assert "Edit envelope" not in cancel_response.text
    stored_envelope = Envelope.get(envelope.id)
    assert stored_envelope is not None
    assert stored_envelope.name == "Trip"
    assert stored_envelope.target_amount == 1_200


def test_edit_form_errors_are_local_to_envelope_tile(client: TestClient) -> None:
    user = User.create(userId=1, username="alice", salary=1_500)
    envelope = Envelope.create(
        user_id=user.id,
        name="Trip",
        target_amount=1_200,
        priority=1,
    )

    response = client.post(
        f"/users/{user.id}/envelopes/{envelope.id}/edit",
        data={"name": "   ", "target_amount": "0"},
    )

    assert response.status_code == 422
    assert 'class="configuration-panel"' in response.text
    assert "Add a name." in response.text
    assert "Use an amount above 0." in response.text
    assert Envelope.get(envelope.id).name == "Trip"  # type: ignore[union-attr]


def test_financial_pillow_name_can_be_edited_but_goal_cannot(
    client: TestClient,
) -> None:
    user = User.create(userId=1, username="alice", salary=1_500)
    envelope = Envelope.create(
        user_id=user.id,
        name="Reserve",
        current_amount=500,
        priority=1,
        kind="financial_pillow",
    )

    name_response = client.patch(
        f"/envelopes/{envelope.id}",
        json={"name": "Safe place"},
    )
    override_response = client.patch(
        f"/envelopes/{envelope.id}",
        json={"name": "Changed", "target_amount": 1},
    )

    assert name_response.status_code == 200
    assert name_response.json()["name"] == "Safe place"
    assert name_response.json()["target_amount"] == 3_000
    assert name_response.json()["current_amount"] == 500
    assert name_response.json()["kind"] == "financial_pillow"
    assert override_response.status_code == 422
    stored_envelope = Envelope.get(envelope.id)
    assert stored_envelope is not None
    assert stored_envelope.name == "Safe place"
    assert stored_envelope.target_amount == 3_000
    assert stored_envelope.kind == "financial_pillow"


def test_financial_pillow_edit_ui_shows_read_only_calculated_goal(
    client: TestClient,
) -> None:
    user = User.create(userId=1, username="alice", salary=1_500)
    envelope = Envelope.create(
        user_id=user.id,
        name="Reserve",
        priority=1,
        kind="financial_pillow",
    )

    response = client.get(
        f"/users/{user.id}/envelopes/page?edit_envelope_id={envelope.id}"
    )

    assert response.status_code == 200
    assert "Edit envelope" in response.text
    assert "€3,000" in response.text
    assert f"edit-envelope-target-{envelope.id}" not in response.text
    assert f"2 {chr(215)} monthly salary" in response.text


@pytest.mark.parametrize(
    ("original_kind", "new_kind"),
    [("regular", "financial_pillow"), ("financial_pillow", "regular")],
)
def test_envelope_kind_cannot_be_changed_during_edit(
    client: TestClient,
    original_kind: str,
    new_kind: str,
) -> None:
    user = User.create(userId=1, username="alice", salary=1_500)
    envelope = Envelope.create(
        user_id=user.id,
        name="Savings",
        target_amount=1_200 if original_kind == "regular" else None,
        priority=1,
        kind=original_kind,
    )
    payload: dict[str, object] = {"name": "Savings", "kind": new_kind}
    if original_kind == "regular":
        payload["target_amount"] = 1_200

    response = client.patch(f"/envelopes/{envelope.id}", json=payload)

    assert response.status_code == 422
    assert Envelope.get(envelope.id).kind == original_kind  # type: ignore[union-attr]


def test_regular_envelope_edit_updates_progress_and_status(client: TestClient) -> None:
    user = User.create(userId=1, username="alice", salary=1_500)
    envelope = Envelope.create(
        user_id=user.id,
        name="Trip",
        current_amount=750,
        target_amount=1_500,
        priority=1,
    )

    response = client.post(
        f"/users/{user.id}/envelopes/{envelope.id}/edit",
        data={"name": "Trip", "target_amount": "1000"},
    )

    assert response.status_code == 200
    assert "75%" in response.text
    assert 'aria-valuenow="75"' in response.text
    assert response.text.count('class="progress-segment is-filled"') == 7
    assert "€250 to go" in response.text
    assert "€750" in response.text


def test_regular_envelope_edit_keeps_savings_above_new_goal(client: TestClient) -> None:
    user = User.create(userId=1, username="alice", salary=1_500)
    envelope = Envelope.create(
        user_id=user.id,
        name="Trip",
        current_amount=1_200,
        target_amount=2_000,
        priority=1,
    )

    response = client.patch(
        f"/envelopes/{envelope.id}",
        json={"name": "Trip", "target_amount": 1_000},
    )
    page_response = client.get(f"/users/{user.id}/envelopes/page")

    assert response.status_code == 200
    assert response.json()["current_amount"] == 1_200
    assert "100%" in page_response.text
    assert "goal reached ✓" in page_response.text
    assert "€1,200" in page_response.text
