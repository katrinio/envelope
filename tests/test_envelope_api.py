from calendar import month_name
from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src import database
from src.app import app
from src.orm.contribution import Contribution
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


def test_envelopes_can_be_reordered_and_order_persists(client: TestClient) -> None:
    user = User.create(userId=1, username="alice", salary=100_000)
    first = Envelope.create(user_id=user.id, name="First", target_amount=100, priority=1)
    second = Envelope.create(user_id=user.id, name="Second", target_amount=100, priority=2)
    third = Envelope.create(user_id=user.id, name="Third", target_amount=100, priority=3)

    response = client.patch(
        f"/users/{user.id}/envelopes/order",
        json={"envelope_ids": [third.id, first.id, second.id]},
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [third.id, first.id, second.id]
    assert [item.name for item in Envelope.for_user(user.id)] == ["Third", "First", "Second"]
    page = client.get(f"/users/{user.id}/envelopes/page")
    assert page.text.index(f'data-envelope-id="{third.id}"') < page.text.index(
        f'data-envelope-id="{first.id}"'
    )


def test_reorder_rejects_unknown_or_duplicate_envelopes(client: TestClient) -> None:
    user = User.create(userId=1, username="alice", salary=100_000)
    envelope = Envelope.create(user_id=user.id, name="First", target_amount=100, priority=1)

    response = client.patch(
        f"/users/{user.id}/envelopes/order",
        json={"envelope_ids": [envelope.id, envelope.id]},
    )

    assert response.status_code == 422


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
    assert response.headers["cache-control"] == "no-cache"


def test_section_tabs_render_with_monthly_spending_empty_by_default(client: TestClient) -> None:
    user = User.create(userId=1, username="alice", salary=100_000)

    response = client.get(f"/users/{user.id}/envelopes/page")

    assert response.status_code == 200
    assert 'data-section-tab="savings"' in response.text
    assert 'data-section-tab="spending"' in response.text
    assert 'data-section-content="spending" hidden' in response.text
    script = client.get("/static/envelope.js")
    assert "finpillow:active-section" in script.text
    assert "setActiveSection(activeSection)" in script.text


def test_static_assets_use_safe_cache_policy(client: TestClient) -> None:
    versioned = client.get("/static/envelope.css?v=build-1")
    unversioned = client.get("/static/envelope.css")

    assert versioned.status_code == 200
    assert versioned.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert unversioned.status_code == 200
    assert unversioned.headers["cache-control"] == "no-cache"


def test_username_is_lowercase_and_has_inline_editor(client: TestClient) -> None:
    user = User.create(userId=1, username="Alice Smith", salary=100_000)

    response = client.get(f"/users/{user.id}/envelopes/page")

    assert response.status_code == 200
    assert ">alice smith</button>" in response.text
    assert 'data-username-editor' in response.text
    assert 'name="username"' in response.text
    assert "data-username-cancel" in response.text


def test_username_can_be_updated_and_cancelled(client: TestClient) -> None:
    user = User.create(userId=1, username="Alice", salary=100_000)

    update_response = client.post(
        f"/users/{user.id}/username/edit",
        data={"username": "Alice Cooper"},
    )

    assert update_response.status_code == 200
    stored_user = User.get(user.id)
    assert stored_user is not None
    assert stored_user.username == "Alice Cooper"
    assert ">alice cooper</button>" in update_response.text

    page_response = client.get(f"/users/{user.id}/envelopes/page")
    assert 'data-current-username="Alice Cooper"' in page_response.text
    assert "data-username-cancel" in page_response.text


@pytest.mark.parametrize("username", ["", "   "])
def test_username_rejects_blank_display_name(
    client: TestClient,
    username: str,
) -> None:
    user = User.create(userId=1, username="Alice", salary=100_000)

    response = client.post(
        f"/users/{user.id}/username/edit",
        data={"username": username},
    )

    assert response.status_code == 422
    assert "Add a display name." in response.text
    assert User.get(user.id).username == "Alice"  # type: ignore[union-attr]


def test_insights_section_is_collapsed_and_contains_three_cards(client: TestClient) -> None:
    user = User.create(userId=1, username="alice", salary=100_000)

    response = client.get(f"/users/{user.id}/envelopes/page")
    stylesheet = Path("src/static/envelope.css").read_text()

    assert response.status_code == 200
    details_tag = response.text.split('<details class="insights-section"', maxsplit=1)[1].split(
        ">", maxsplit=1
    )[0]
    assert "open" not in details_tag
    assert "Insights" in response.text
    assert response.text.count('class="insight-card"') == 3
    assert "How am I saving?" in response.text
    assert "How close are my goals?" in response.text
    assert "What needs attention?" in response.text
    assert "No regular contribution history yet." in response.text
    assert "No active savings goals right now." in response.text
    assert ".insights-list" in stylesheet
    assert "width: 100%;" in stylesheet


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

    increment_response = client.post(
        amount_url,
        data={
            "amount": 50,
            "operation": "increment",
            "regular_contribution": ["false", "true"],
        },
    )
    assert increment_response.status_code == 200
    assert client.get(f"/envelopes/{envelope['id']}").json()["current_amount"] == 150
    contributions = Contribution.for_envelope(envelope["id"])
    assert len(contributions) == 1
    assert contributions[0].amount == 50
    assert contributions[0].is_regular is True
    assert contributions[0].contributed_at is not None

    decrement_response = client.post(amount_url, data={"amount": 25, "operation": "decrement"})
    assert decrement_response.status_code == 200
    assert client.get(f"/envelopes/{envelope['id']}").json()["current_amount"] == 125
    transactions = Contribution.for_envelope(envelope["id"])
    assert len(transactions) == 2
    assert transactions[1].is_withdrawal is True
    assert transactions[1].amount == 25


def test_add_money_shows_regular_contribution_checked_by_default(client: TestClient) -> None:
    user = User.create(userId=1, username="alice", salary=100_000)
    envelope = Envelope.create(
        user_id=user.id,
        name="Emergency fund",
        target_amount=1_000,
        priority=1,
    )

    response = client.get(f"/users/{user.id}/envelopes/page")

    assert response.status_code == 200
    assert response.text.count("Regular contribution") == 1
    checkbox = response.text.split('name="regular_contribution"', maxsplit=2)[2].split(
        ">", maxsplit=1
    )[0]
    assert 'type="checkbox"' in checkbox
    assert "checked" in checkbox
    assert f"amount-increment-{envelope.id}" in response.text


def test_non_regular_contribution_is_persisted(client: TestClient) -> None:
    user = User.create(userId=1, username="alice", salary=100_000)
    envelope = Envelope.create(
        user_id=user.id,
        name="Emergency fund",
        current_amount=100,
        target_amount=1_000,
        priority=1,
    )

    response = client.post(
        f"/users/{user.id}/envelopes/{envelope.id}/amount",
        data={
            "amount": "40",
            "operation": "increment",
            "regular_contribution": "false",
        },
    )

    assert response.status_code == 200
    stored_envelope = Envelope.get(envelope.id)
    assert stored_envelope is not None
    assert stored_envelope.current_amount == 140
    contributions = Contribution.for_envelope(envelope.id)
    assert len(contributions) == 1
    assert contributions[0].amount == 40
    assert contributions[0].is_regular is False
    assert contributions[0].contributed_at is not None


def test_saving_insight_combines_regular_contributions_from_all_envelopes(
    client: TestClient,
) -> None:
    user = User.create(userId=1, username="alice", salary=1_000)
    first_envelope = Envelope.create(
        user_id=user.id,
        name="Emergency fund",
        target_amount=10_000,
        priority=1,
    )
    second_envelope = Envelope.create(
        user_id=user.id,
        name="Trip",
        target_amount=5_000,
        priority=2,
    )
    current_month = date.today().replace(day=1)
    current_month_index = current_month.year * 12 + current_month.month - 1

    for offset, envelope_id, amount in [
        (-3, first_envelope.id, 100),
        (-2, second_envelope.id, 200),
        (-1, first_envelope.id, 300),
    ]:
        year, zero_based_month = divmod(current_month_index + offset, 12)
        Contribution.create(
            envelope_id=envelope_id,
            amount=amount,
            is_regular=True,
            contributed_at=datetime(year, zero_based_month + 1, 10),
        )

    previous_year, previous_month = divmod(current_month_index - 1, 12)
    Contribution.create(
        envelope_id=second_envelope.id,
        amount=9_000,
        is_regular=False,
        contributed_at=datetime(previous_year, previous_month + 1, 12),
    )
    Contribution.create(
        envelope_id=second_envelope.id,
        amount=8_000,
        is_regular=True,
        contributed_at=datetime(current_month.year, current_month.month, 1),
    )

    response = client.get(f"/users/{user.id}/envelopes/page")

    assert response.status_code == 200
    assert '<strong>20%</strong>' in response.text
    assert "€200/month on average" in response.text
    assert "over the last 3 complete" in response.text
    assert "months" in response.text
    assert "9,000/month" not in response.text


def test_goal_projections_use_each_envelopes_regular_contributions(
    client: TestClient,
) -> None:
    user = User.create(userId=1, username="alice", salary=1_000)
    projected = Envelope.create(
        user_id=user.id,
        name="Trip",
        current_amount=3_800,
        target_amount=5_000,
        priority=1,
    )
    no_history = Envelope.create(
        user_id=user.id,
        name="Camera",
        current_amount=200,
        target_amount=1_000,
        priority=2,
    )
    Envelope.create(
        user_id=user.id,
        name="Completed",
        current_amount=1_000,
        target_amount=1_000,
        priority=3,
    )
    current_month = date.today().replace(day=1)
    current_month_index = current_month.year * 12 + current_month.month - 1

    for offset in range(-3, 0):
        year, zero_based_month = divmod(current_month_index + offset, 12)
        Contribution.create(
            envelope_id=projected.id,
            amount=400,
            is_regular=True,
            contributed_at=datetime(year, zero_based_month + 1, 10),
        )

    previous_year, previous_month = divmod(current_month_index - 1, 12)
    Contribution.create(
        envelope_id=projected.id,
        amount=3_000,
        is_regular=False,
        contributed_at=datetime(previous_year, previous_month + 1, 12),
    )

    completion_year, completion_month_index = divmod(current_month_index + 3, 12)
    expected_completion = f"{month_name[completion_month_index + 1]} {completion_year}"
    response = client.get(f"/users/{user.id}/envelopes/page")

    assert response.status_code == 200
    assert "Trip" in response.text
    assert "€1,200 to go" in response.text
    assert f"<strong>{expected_completion}</strong>" in response.text
    assert "Camera" in response.text
    assert "€800 to go" in response.text
    assert "Not enough data to estimate yet." in response.text
    insights_html = response.text.split('<div class="insights-list">', maxsplit=1)[1]
    assert "Completed" not in insights_html
    assert no_history.current_amount == 200


def test_attention_insight_is_rendered_for_specific_pace_drop(client: TestClient) -> None:
    user = User.create(userId=1, username="alice", salary=1_000)
    envelope = Envelope.create(
        user_id=user.id,
        name="Trip",
        current_amount=100,
        target_amount=1_000,
        priority=1,
    )
    current_month = date.today().replace(day=1)
    current_month_index = current_month.year * 12 + current_month.month - 1
    for offset, amount in [(-6, 200), (-5, 200), (-4, 200), (-3, 100), (-2, 100), (-1, 100)]:
        year, zero_based_month = divmod(current_month_index + offset, 12)
        Contribution.create(
            envelope_id=envelope.id,
            amount=amount,
            is_regular=True,
            contributed_at=datetime(year, zero_based_month + 1, 1),
        )

    response = client.get(f"/users/{user.id}/envelopes/page")

    assert response.status_code == 200
    assert "What needs attention?" in response.text
    assert "Trip" in response.text
    assert "Your recent saving pace is 50% lower than in the previous 3 months." in response.text
    assert "Nothing needs your attention right now." not in response.text


def test_decrement_below_zero_renders_local_amount_error(client: TestClient) -> None:
    user = User.create(userId=1, username="alice", salary=100_000)
    envelope = Envelope.create(
        user_id=user.id,
        name="Emergency fund",
        current_amount=10,
        target_amount=1_000,
        priority=1,
    )

    response = client.post(
        f"/users/{user.id}/envelopes/{envelope.id}/amount",
        data={"amount": "20", "operation": "decrement"},
    )

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("text/html")
    assert "Saved amount cannot go below €0." in response.text
    assert '<details class="adjustment-control" open>' in response.text
    assert 'value="20"' in response.text
    assert 'aria-invalid="true"' in response.text
    stored_envelope = Envelope.get(envelope.id)
    assert stored_envelope is not None
    assert stored_envelope.current_amount == 10


@pytest.mark.parametrize(
    ("amount", "message"),
    [("0", "Use an amount above 0."), ("abc", "Enter a whole amount.")],
)
def test_invalid_amount_renders_local_error(
    client: TestClient,
    amount: str,
    message: str,
) -> None:
    user = User.create(userId=1, username="alice", salary=100_000)
    envelope = Envelope.create(
        user_id=user.id,
        name="Emergency fund",
        current_amount=10,
        target_amount=1_000,
        priority=1,
    )

    response = client.post(
        f"/users/{user.id}/envelopes/{envelope.id}/amount",
        data={"amount": amount, "operation": "decrement"},
    )

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("text/html")
    assert message in response.text
    assert f'value="{amount}"' in response.text
    assert Envelope.get(envelope.id).current_amount == 10  # type: ignore[union-attr]


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
    assert 'class="device-menu-trigger"' in response.text
    assert 'aria-label="Envelope actions"' in response.text
    assert 'role="menu"' in response.text
    assert "•••" in response.text
    assert "History" in response.text
    assert "Edit" in response.text
    assert "Delete" in response.text
    assert f"?edit_envelope_id={envelope.id}" in response.text
    assert f'data-delete-url="http://testserver/envelopes/{envelope.id}"' in response.text
    assert "Permanently delete this envelope? This action cannot be undone." in response.text
    assert "real money" not in response.text.lower()
    assert "data-delete-dialog" in response.text
    assert "data-delete-confirm" in response.text
    assert "data-delete-cancel" in response.text
    assert '<details class="device-menu"' not in response.text

    script_response = client.get("/static/envelope.js")
    assert script_response.status_code == 200
    assert "real money" not in script_response.text.lower()
    assert "deleteDialog.showModal()" in script_response.text
    assert 'method: "DELETE"' in script_response.text
    assert "closeOtherInteractions" in script_response.text
    assert 'querySelectorAll(".adjustment-control")' in script_response.text
    assert 'long-term-savings:insights-expanded' in script_response.text
    assert 'localStorage.setItem(insightsStorageKey, String(insightsSection.open))' in script_response.text


def test_history_panel_lists_transactions_newest_first(client: TestClient) -> None:
    user = User.create(userId=1, username="alice", salary=1_500)
    envelope = Envelope.create(
        user_id=user.id,
        name="Pillow",
        current_amount=100,
        target_amount=1_000,
        priority=1,
    )
    Contribution.create(
        envelope_id=envelope.id,
        amount=50,
        is_regular=True,
        transaction_type="contribution",
        contributed_at=datetime(2026, 7, 30, 12),
    )
    Contribution.create(
        envelope_id=envelope.id,
        amount=20,
        is_regular=False,
        transaction_type="contribution",
        contributed_at=datetime(2026, 8, 20, 12),
    )
    Contribution.create(
        envelope_id=envelope.id,
        amount=20,
        is_regular=False,
        transaction_type="withdrawal",
        contributed_at=datetime(2026, 8, 26, 12),
    )

    response = client.get(
        f"/users/{user.id}/envelopes/page?history_envelope_id={envelope.id}"
    )

    assert response.status_code == 200
    assert "Pillow — History" in response.text
    assert "AUGUST 26" in response.text
    assert "JULY 30" in response.text
    assert "−" in response.text  # noqa: RUF001
    assert "Regular contribution" in response.text
    assert "One-time contribution" in response.text
    assert response.text.index("AUGUST 26") < response.text.index("JULY 30")
    assert "Edit" in response.text
    assert "Permanently delete this transaction? This action cannot be undone." in response.text


def test_history_modal_has_viewport_backdrop_and_close_control(client: TestClient) -> None:
    user = User.create(userId=1, username="alice", salary=1_500)
    envelope = Envelope.create(user_id=user.id, name="Trip", target_amount=1_000, priority=1)

    response = client.get(
        f"/users/{user.id}/envelopes/page?history_envelope_id={envelope.id}"
    )
    stylesheet = Path("src/static/envelope.css").read_text()

    assert 'data-history-backdrop aria-hidden="true"' in response.text
    assert 'aria-label="Close history"' in response.text
    assert "background: rgb(0 0 0 / 22%)" in stylesheet
    assert "z-index: 1000" in stylesheet
    assert "z-index: 1001" in stylesheet


def test_history_cannot_be_opened_for_another_users_envelope(client: TestClient) -> None:
    owner = User.create(userId=1, username="alice", salary=1_500)
    other_user = User.create(userId=2, username="bob", salary=1_500)
    envelope = Envelope.create(user_id=other_user.id, name="Private", target_amount=1_000, priority=1)

    response = client.get(
        f"/users/{owner.id}/envelopes/page?history_envelope_id={envelope.id}"
    )

    assert response.status_code == 404


def test_history_editing_withdrawal_recalculates_balance(client: TestClient) -> None:
    user = User.create(userId=1, username="alice", salary=1_500)
    envelope = Envelope.create(
        user_id=user.id,
        name="Trip",
        current_amount=100,
        target_amount=1_000,
        priority=1,
    )
    transaction = Contribution.withdraw_from_envelope(envelope.id, 30)

    response = client.post(
        f"/users/{user.id}/envelopes/{envelope.id}/history/{transaction.id}/edit",
        data={"amount": "50", "transaction_date": "2026-08-26"},
    )

    assert response.status_code == 200
    stored_envelope = Envelope.get(envelope.id)
    stored_transaction = Contribution.get(transaction.id)
    assert stored_envelope is not None
    assert stored_transaction is not None
    assert stored_envelope.current_amount == 50
    assert stored_transaction.is_withdrawal is True
    assert stored_transaction.is_regular is False


def test_history_edit_recalculates_balance_and_regular_status(client: TestClient) -> None:
    user = User.create(userId=1, username="alice", salary=1_500)
    envelope = Envelope.create(
        user_id=user.id,
        name="Trip",
        current_amount=100,
        target_amount=1_000,
        priority=1,
    )
    transaction = Contribution.add_to_envelope(envelope.id, 50, is_regular=True)

    response = client.post(
        f"/users/{user.id}/envelopes/{envelope.id}/history/{transaction.id}/edit",
        data={
            "amount": "40",
            "transaction_date": "2026-07-15",
            "regular_contribution": ["false", "false"],
        },
    )

    assert response.status_code == 200
    stored_envelope = Envelope.get(envelope.id)
    stored_transaction = Contribution.get(transaction.id)
    assert stored_envelope is not None
    assert stored_transaction is not None
    assert stored_envelope.current_amount == 140
    assert stored_transaction.amount == 40
    assert stored_transaction.is_regular is False
    assert stored_transaction.contributed_at.date() == date(2026, 7, 15)


def test_history_delete_recalculates_balance_and_removes_transaction(client: TestClient) -> None:
    user = User.create(userId=1, username="alice", salary=1_500)
    envelope = Envelope.create(
        user_id=user.id,
        name="Trip",
        current_amount=100,
        target_amount=1_000,
        priority=1,
    )
    transaction = Contribution.add_to_envelope(envelope.id, 50)

    response = client.post(
        f"/users/{user.id}/envelopes/{envelope.id}/history/{transaction.id}/delete"
    )

    assert response.status_code == 200
    stored_envelope = Envelope.get(envelope.id)
    assert stored_envelope is not None
    assert stored_envelope.current_amount == 100
    assert Contribution.get(transaction.id) is None
    history_response = client.get(
        f"/users/{user.id}/envelopes/page?history_envelope_id={envelope.id}"
    )
    assert "No transactions yet." in history_response.text


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
    assert 'class="device-screen configuration-screen"' in response.text
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
    assert 'class="envelope-device"' in response.text
    assert 'class="device-screen configuration-screen"' in response.text
    assert "€3,000" in response.text
    assert f"edit-envelope-target-{envelope.id}" not in response.text
    assert f"amount-increment-{envelope.id}" not in response.text
    assert f"amount-decrement-{envelope.id}" not in response.text
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


def test_salary_is_rendered_as_inline_editor_in_header(client: TestClient) -> None:
    user = User.create(userId=1, username="alice", salary=100_000)

    response = client.get(f"/users/{user.id}/envelopes/page")

    assert response.status_code == 200
    assert "€100,000" in response.text
    assert 'class="salary-display"' in response.text
    assert 'aria-label="Edit monthly salary, currently €100,000"' in response.text
    assert 'class="salary-form"' in response.text
    assert 'value="100000"' in response.text
    assert "hidden" in response.text
    assert "/static/envelope.js?v=20260827-1" in response.text


def test_salary_can_be_updated(client: TestClient) -> None:
    user = User.create(userId=1, username="alice", salary=1_500)

    response = client.patch(
        f"/users/{user.id}/salary",
        json={"salary": 1_700},
    )

    assert response.status_code == 200
    assert response.json() == {"id": user.id, "salary": 1_700}
    stored_user = User.get(user.id)
    assert stored_user is not None
    assert stored_user.salary == 1_700


@pytest.mark.parametrize("salary", [0, -1])
def test_salary_backend_rejects_non_positive_value(
    client: TestClient,
    salary: int,
) -> None:
    user = User.create(userId=1, username="alice", salary=1_500)

    response = client.patch(
        f"/users/{user.id}/salary",
        json={"salary": salary},
    )

    assert response.status_code == 422
    assert User.get(user.id).salary == 1_500  # type: ignore[union-attr]


@pytest.mark.parametrize(
    ("salary", "message"),
    [("", "Enter a whole amount."), ("abc", "Enter a whole amount."), ("0", "Use an amount above 0.")],
)
def test_invalid_salary_renders_local_error(
    client: TestClient,
    salary: str,
    message: str,
) -> None:
    user = User.create(userId=1, username="alice", salary=1_500)

    response = client.post(
        f"/users/{user.id}/salary/edit",
        data={"salary": salary},
    )

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("text/html")
    assert message in response.text
    assert 'class="salary-error"' in response.text
    assert 'aria-invalid="true"' in response.text
    assert User.get(user.id).salary == 1_500  # type: ignore[union-attr]


def test_salary_edit_cancel_does_not_persist(client: TestClient) -> None:
    user = User.create(userId=1, username="alice", salary=1_500)

    page_response = client.get(f"/users/{user.id}/envelopes/page")
    script_response = client.get("/static/envelope.js")

    assert page_response.status_code == 200
    assert 'data-current-salary="1500"' in page_response.text
    assert "data-salary-cancel" in page_response.text
    assert "salaryInput.value = salaryEditor.dataset.currentSalary" in script_response.text
    stored_user = User.get(user.id)
    assert stored_user is not None
    assert stored_user.salary == 1_500


def test_salary_change_preserves_regular_goal_and_recalculates_pillow(
    client: TestClient,
) -> None:
    user = User.create(userId=1, username="alice", salary=1_000)
    regular = Envelope.create(
        user_id=user.id,
        name="Trip",
        current_amount=250,
        target_amount=2_500,
        priority=1,
    )
    pillow = Envelope.create(
        user_id=user.id,
        name="Reserve",
        current_amount=3_000,
        priority=2,
        kind="financial_pillow",
        pillow_index=3,
    )

    response = client.post(
        f"/users/{user.id}/salary/edit",
        data={"salary": "2000"},
    )

    assert response.status_code == 200
    assert "€2,000" in response.text
    assert "€6,000" in response.text
    assert f"3 {chr(215)} monthly salary" in response.text
    assert "50%" in response.text
    assert 'aria-valuenow="50"' in response.text
    assert response.text.count('class="progress-segment is-filled"') == 6
    assert "€3,000 to go" in response.text
    stored_regular = Envelope.get(regular.id)
    stored_pillow = Envelope.get(pillow.id)
    assert stored_regular is not None
    assert stored_pillow is not None
    assert stored_regular.target_amount == 2_500
    assert stored_pillow.target_amount == 6_000
    assert stored_pillow.pillow_index == 3
    assert stored_pillow.current_amount == 3_000
