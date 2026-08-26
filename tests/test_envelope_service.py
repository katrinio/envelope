from datetime import date, datetime

from src.envelope.service import (
    GoalHistory,
    calculate_attention_observations,
    calculate_goal_projection,
    calculate_saving_insight,
)


def test_saving_insight_uses_last_three_complete_months_and_shows_trend() -> None:
    insight = calculate_saving_insight(
        monthly_salary=1_000,
        regular_contributions=[
            (200, datetime(2026, 2, 5)),
            (200, datetime(2026, 3, 5)),
            (200, datetime(2026, 4, 5)),
            (300, datetime(2026, 5, 5)),
            (300, datetime(2026, 6, 5)),
            (300, datetime(2026, 7, 5)),
            (5_000, datetime(2026, 8, 1)),
        ],
        today=date(2026, 8, 26),
    )

    assert insight is not None
    assert insight.average_monthly_amount == 300
    assert insight.average_saving_rate == 30
    assert insight.months_count == 3
    assert insight.trend_message == "↑ 10 pp vs previous 3 months"


def test_saving_insight_uses_available_complete_months_and_counts_gaps() -> None:
    insight = calculate_saving_insight(
        monthly_salary=1_000,
        regular_contributions=[(100, date(2026, 6, 12))],
        today=date(2026, 8, 26),
    )

    assert insight is not None
    assert insight.average_monthly_amount == 50
    assert insight.average_saving_rate == 5
    assert insight.months_count == 2
    assert insight.trend_message is None


def test_saving_insight_uses_neutral_trend_for_small_difference() -> None:
    insight = calculate_saving_insight(
        monthly_salary=1_000,
        regular_contributions=[
            (100, date(2026, 2, 1)),
            (100, date(2026, 3, 1)),
            (100, date(2026, 4, 1)),
            (105, date(2026, 5, 1)),
            (105, date(2026, 6, 1)),
            (105, date(2026, 7, 1)),
        ],
        today=date(2026, 8, 26),
    )

    assert insight is not None
    assert insight.trend_message == "About the same as before"


def test_saving_insight_reports_downward_difference_in_percentage_points() -> None:
    insight = calculate_saving_insight(
        monthly_salary=1_000,
        regular_contributions=[
            (200, date(2026, 2, 1)),
            (200, date(2026, 3, 1)),
            (200, date(2026, 4, 1)),
            (100, date(2026, 5, 1)),
            (100, date(2026, 6, 1)),
            (100, date(2026, 7, 1)),
        ],
        today=date(2026, 8, 26),
    )

    assert insight is not None
    assert insight.trend_message == "↓ 10 pp vs previous 3 months"


def test_saving_insight_has_empty_state_without_complete_month_history() -> None:
    insight = calculate_saving_insight(
        monthly_salary=1_000,
        regular_contributions=[(100, date(2026, 8, 1))],
        today=date(2026, 8, 26),
    )

    assert insight is None


def test_goal_projection_uses_envelope_pace_and_rounds_months_up() -> None:
    projection = calculate_goal_projection(
        envelope_id=1,
        envelope_name="Trip",
        current_amount=800,
        target_amount=2_000,
        regular_contributions=[
            (400, date(2026, 5, 1)),
            (400, date(2026, 6, 1)),
            (400, date(2026, 7, 1)),
            (9_000, date(2026, 8, 1)),
        ],
        today=date(2026, 8, 26),
    )

    assert projection is not None
    assert projection.remaining_amount == 1_200
    assert projection.completion_month == "November 2026"


def test_goal_projection_uses_limited_complete_history() -> None:
    projection = calculate_goal_projection(
        envelope_id=1,
        envelope_name="Trip",
        current_amount=200,
        target_amount=1_000,
        regular_contributions=[(400, date(2026, 7, 10))],
        today=date(2026, 8, 26),
    )

    assert projection is not None
    assert projection.completion_month == "October 2026"


def test_goal_projection_omits_date_without_recent_regular_history() -> None:
    projection = calculate_goal_projection(
        envelope_id=1,
        envelope_name="Trip",
        current_amount=200,
        target_amount=1_000,
        regular_contributions=[(400, date(2026, 8, 1))],
        today=date(2026, 8, 26),
    )

    assert projection is not None
    assert projection.remaining_amount == 800
    assert projection.completion_month is None


def test_goal_projection_excludes_completed_goal() -> None:
    projection = calculate_goal_projection(
        envelope_id=1,
        envelope_name="Trip",
        current_amount=1_200,
        target_amount=1_000,
        regular_contributions=[(100, date(2026, 7, 1))],
        today=date(2026, 8, 26),
    )

    assert projection is None


def test_attention_prioritizes_stalled_goals_and_limits_observations() -> None:
    histories = tuple(
        GoalHistory(
            envelope_id=envelope_id,
            envelope_name=f"Goal {envelope_id}",
            current_amount=100,
            target_amount=1_000,
            regular_contributions=(
                (100, date(2026, 4, 1)),
                (100, date(2026, 5, 1)),
            ),
        )
        for envelope_id in range(1, 5)
    )

    observations = calculate_attention_observations(
        monthly_salary=1_000,
        goal_histories=histories,
        today=date(2026, 8, 26),
    )

    assert len(observations) == 3
    assert [observation.title for observation in observations] == [
        "Goal 1",
        "Goal 2",
        "Goal 3",
    ]
    assert all("No regular contributions for 2 months." in observation.message for observation in observations)


def test_attention_reports_specific_pace_drop_without_general_duplicate() -> None:
    history = GoalHistory(
        envelope_id=1,
        envelope_name="Trip",
        current_amount=100,
        target_amount=1_000,
        regular_contributions=tuple(
            (amount, date(year, month, 1))
            for year, month, amount in [
                (2026, 2, 200),
                (2026, 3, 200),
                (2026, 4, 200),
                (2026, 5, 100),
                (2026, 6, 100),
                (2026, 7, 100),
            ]
        ),
    )

    observations = calculate_attention_observations(
        monthly_salary=1_000,
        goal_histories=[history],
        today=date(2026, 8, 26),
    )

    assert len(observations) == 1
    assert observations[0].title == "Trip"
    assert "50% lower" in observations[0].message
    assert "Saving pace" not in observations[0].title


def test_attention_reports_overall_rate_drop_when_no_specific_goal_drop() -> None:
    histories = [
        GoalHistory(
            envelope_id=1,
            envelope_name="A",
            current_amount=100,
            target_amount=1_000,
            regular_contributions=tuple(
                (amount, date(year, month, 1))
                for year, month, amount in [
                    (2026, 2, 201),
                    (2026, 3, 201),
                    (2026, 4, 201),
                    (2026, 5, 151),
                    (2026, 6, 151),
                    (2026, 7, 151),
                ]
            ),
        ),
        GoalHistory(
            envelope_id=2,
            envelope_name="B",
            current_amount=100,
            target_amount=1_000,
            regular_contributions=tuple(
                (100, date(year, month, 1))
                for year, month in [
                    (2026, 2),
                    (2026, 3),
                    (2026, 4),
                    (2026, 5),
                    (2026, 6),
                    (2026, 7),
                ]
            ),
        ),
    ]

    observations = calculate_attention_observations(
        monthly_salary=1_000,
        goal_histories=histories,
        today=date(2026, 8, 26),
    )

    assert len(observations) == 1
    assert observations[0].title == "Saving pace"
    assert "5 pp lower" in observations[0].message
