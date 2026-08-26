from datetime import date, datetime

from src.envelope.service import calculate_saving_insight


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
