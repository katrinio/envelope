from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

FINANCIAL_PILLOW_SALARY_MULTIPLIER = 2


@dataclass(frozen=True)
class SavingInsight:
    average_monthly_amount: int
    average_saving_rate: int
    months_count: int
    trend_message: str | None


def calculate_financial_pillow_target(
    monthly_salary: int,
    pillow_index: int = FINANCIAL_PILLOW_SALARY_MULTIPLIER,
) -> int:
    if monthly_salary <= 0:
        raise ValueError("A positive salary is needed for a financial pillow.")
    if pillow_index <= 0:
        raise ValueError("A positive pillow index is required.")
    return monthly_salary * pillow_index


def _shift_month(month: date, offset: int) -> date:
    month_index = month.year * 12 + month.month - 1 + offset
    year, zero_based_month = divmod(month_index, 12)
    return date(year, zero_based_month + 1, 1)


def _month_count(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + end.month - start.month


def _round_decimal(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _as_date(value: date | datetime) -> date:
    return value.date() if isinstance(value, datetime) else value


def calculate_saving_insight(
    monthly_salary: int,
    regular_contributions: Iterable[tuple[int, date | datetime]],
    today: date | None = None,
) -> SavingInsight | None:
    if monthly_salary <= 0:
        return None

    current_month = (today or date.today()).replace(day=1)
    dated_amounts = [
        (amount, contribution_date)
        for amount, contributed_at in regular_contributions
        if (contribution_date := _as_date(contributed_at)) < current_month
    ]
    if not dated_amounts:
        return None

    main_period_start = _shift_month(current_month, -3)
    main_contributions = [
        (amount, contributed_at)
        for amount, contributed_at in dated_amounts
        if main_period_start <= contributed_at < current_month
    ]
    if not main_contributions:
        return None

    first_history_month = min(contributed_at for _, contributed_at in dated_amounts).replace(day=1)
    available_start = max(main_period_start, first_history_month)
    months_count = _month_count(available_start, current_month)
    total_saved = sum(
        amount
        for amount, contributed_at in main_contributions
        if contributed_at >= available_start
    )
    average_amount = Decimal(total_saved) / months_count
    average_rate = average_amount / monthly_salary * 100

    trend_message: str | None = None
    previous_period_start = _shift_month(current_month, -6)
    if months_count == 3 and first_history_month <= previous_period_start:
        previous_total = sum(
            amount
            for amount, contributed_at in dated_amounts
            if previous_period_start <= contributed_at < main_period_start
        )
        previous_rate = Decimal(previous_total) / 3 / monthly_salary * 100
        difference = average_rate - previous_rate
        if abs(difference) < 1:
            trend_message = "About the same as before"
        else:
            direction = "↑" if difference > 0 else "↓"
            difference_points = _round_decimal(abs(difference))
            trend_message = f"{direction} {difference_points} pp vs previous 3 months"

    return SavingInsight(
        average_monthly_amount=_round_decimal(average_amount),
        average_saving_rate=_round_decimal(average_rate),
        months_count=months_count,
        trend_message=trend_message,
    )
