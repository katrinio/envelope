from calendar import month_name
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

FINANCIAL_PILLOW_SALARY_MULTIPLIER = 2


@dataclass(frozen=True)
class SavingInsight:
    average_monthly_amount: int
    average_saving_rate: int
    months_count: int
    trend_message: str | None


@dataclass(frozen=True)
class GoalProjection:
    envelope_id: int
    envelope_name: str
    remaining_amount: int
    completion_month: str | None


@dataclass(frozen=True)
class GoalHistory:
    envelope_id: int
    envelope_name: str
    current_amount: int
    target_amount: int
    regular_contributions: tuple[tuple[int, date | datetime], ...]


@dataclass(frozen=True)
class AttentionObservation:
    title: str
    message: str


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


def calculate_goal_projection(
    envelope_id: int,
    envelope_name: str,
    current_amount: int,
    target_amount: int,
    regular_contributions: Iterable[tuple[int, date | datetime]],
    today: date | None = None,
) -> GoalProjection | None:
    remaining_amount = target_amount - current_amount
    if remaining_amount <= 0:
        return None

    current_month = (today or date.today()).replace(day=1)
    dated_amounts = [
        (amount, contribution_date)
        for amount, contributed_at in regular_contributions
        if (contribution_date := _as_date(contributed_at)) < current_month
    ]
    main_period_start = _shift_month(current_month, -3)
    main_contributions = [
        (amount, contributed_at)
        for amount, contributed_at in dated_amounts
        if main_period_start <= contributed_at < current_month
    ]
    completion_month: str | None = None
    if main_contributions:
        first_history_month = min(contributed_at for _, contributed_at in dated_amounts).replace(
            day=1
        )
        available_start = max(main_period_start, first_history_month)
        months_count = _month_count(available_start, current_month)
        total_saved = sum(
            amount
            for amount, contributed_at in main_contributions
            if contributed_at >= available_start
        )
        average_amount = Decimal(total_saved) / months_count
        months_remaining = int(
            (Decimal(remaining_amount) / average_amount).to_integral_value(
                rounding=ROUND_CEILING
            )
        )
        completion_date = _shift_month(current_month, months_remaining)
        completion_month = f"{month_name[completion_date.month]} {completion_date.year}"

    return GoalProjection(
        envelope_id=envelope_id,
        envelope_name=envelope_name,
        remaining_amount=remaining_amount,
        completion_month=completion_month,
    )


def calculate_attention_observations(
    monthly_salary: int,
    goal_histories: Iterable[GoalHistory],
    today: date | None = None,
) -> list[AttentionObservation]:
    histories = list(goal_histories)
    if monthly_salary <= 0:
        return []

    current_month = (today or date.today()).replace(day=1)
    previous_period_start = _shift_month(current_month, -6)
    recent_period_start = _shift_month(current_month, -3)
    recent_stalled_start = _shift_month(current_month, -2)

    def complete_dated_amounts(
        contributions: Iterable[tuple[int, date | datetime]],
    ) -> list[tuple[int, date]]:
        return [
            (amount, contribution_date)
            for amount, contributed_at in contributions
            if (contribution_date := _as_date(contributed_at)) < current_month
        ]

    all_contributions = [
        contribution
        for history in histories
        for contribution in history.regular_contributions
    ]
    all_dated_amounts = complete_dated_amounts(all_contributions)
    observations: list[AttentionObservation] = []
    stalled_ids: set[int] = set()
    pace_drop_observations: list[tuple[int, AttentionObservation]] = []

    for history in histories:
        if history.current_amount >= history.target_amount:
            continue

        dated_amounts = complete_dated_amounts(history.regular_contributions)
        history_months = {
            contribution_date.replace(day=1)
            for _, contribution_date in dated_amounts
            if contribution_date < recent_stalled_start
        }
        recent_stalled_contributions = [
            contribution_date
            for _, contribution_date in dated_amounts
            if recent_stalled_start <= contribution_date < current_month
        ]
        if len(history_months) >= 2 and not recent_stalled_contributions:
            stalled_ids.add(history.envelope_id)
            observations.append(
                AttentionObservation(
                    title=history.envelope_name,
                    message="No regular contributions for 2 months.",
                )
            )

        first_history_month = (
            min(contribution_date for _, contribution_date in dated_amounts).replace(day=1)
            if dated_amounts
            else None
        )
        if first_history_month is None or first_history_month > previous_period_start:
            continue

        previous_total = sum(
            amount
            for amount, contribution_date in dated_amounts
            if previous_period_start <= contribution_date < recent_period_start
        )
        recent_total = sum(
            amount
            for amount, contribution_date in dated_amounts
            if recent_period_start <= contribution_date < current_month
        )
        if previous_total <= 0:
            continue

        drop_percentage = (Decimal(previous_total - recent_total) / previous_total) * 100
        if drop_percentage >= 25:
            pace_drop_observations.append(
                (
                    history.envelope_id,
                    AttentionObservation(
                        title=history.envelope_name,
                        message=(
                            "Your recent saving pace is "
                            f"{_round_decimal(drop_percentage)}% lower than in the previous 3 months."
                        ),
                    ),
                )
            )

    observations.extend(
        observation
        for envelope_id, observation in pace_drop_observations
        if envelope_id not in stalled_ids
    )

    if (
        all_dated_amounts
        and min(contribution_date for _, contribution_date in all_dated_amounts).replace(day=1)
        <= previous_period_start
    ):
        previous_total = sum(
            amount
            for amount, contribution_date in all_dated_amounts
            if previous_period_start <= contribution_date < recent_period_start
        )
        recent_total = sum(
            amount
            for amount, contribution_date in all_dated_amounts
            if recent_period_start <= contribution_date < current_month
        )
        previous_rate = Decimal(previous_total) / 3 / monthly_salary * 100
        recent_rate = Decimal(recent_total) / 3 / monthly_salary * 100
        drop_points = previous_rate - recent_rate
        if drop_points >= 5 and not pace_drop_observations:
            observations.append(
                AttentionObservation(
                    title="Saving pace",
                    message=(
                        "Your regular saving rate is "
                        f"{_round_decimal(drop_points)} pp lower than in the previous 3 months."
                    ),
                )
            )

    return observations[:3]
