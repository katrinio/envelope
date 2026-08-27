from calendar import month_name
from dataclasses import dataclass
from datetime import date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.envelope.service import (
    FINANCIAL_PILLOW_SALARY_MULTIPLIER,
    GoalHistory,
    calculate_attention_observations,
    calculate_financial_pillow_target,
    calculate_goal_projection,
    calculate_saving_insight,
)
from src.orm.contribution import Contribution
from src.orm.envelope import Envelope, EnvelopeKind
from src.orm.spending import (
    ActualSpending,
    PlannedSpending,
    RoutineSpending,
    RoutineSpendingSelection,
    SIGNIFICANT_SPENDING_THRESHOLD,
    SpendingPool,
    monthly_money_state,
    spend_planned_item,
    spend_routine_for_month,
)
from src.orm.user import User
from src.template import templates

router = APIRouter(tags=["envelopes"])


class EnvelopeCreate(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=255)]
    current_amount: Annotated[int, Field(ge=0)] = 0
    target_amount: int | None = None
    priority: Annotated[int, Field(gt=0)]
    kind: EnvelopeKind = EnvelopeKind.REGULAR

    @model_validator(mode="after")
    def validate_target_amount(self) -> EnvelopeCreate:
        if self.kind == EnvelopeKind.REGULAR and (
            self.target_amount is None or self.target_amount <= 0
        ):
            raise ValueError("target_amount must be greater than 0")
        return self


class EnvelopeCurrentAmountUpdate(BaseModel):
    current_amount: Annotated[int, Field(ge=0)]


class EnvelopeConfigurationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(max_length=255)]
    target_amount: int | None = None


class SalaryUpdate(BaseModel):
    salary: Annotated[int, Field(gt=0)]


class EnvelopeOrderUpdate(BaseModel):
    envelope_ids: list[int]


class SalaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    salary: int


class EnvelopeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    name: str
    current_amount: int
    target_amount: int
    priority: int
    kind: EnvelopeKind
    pillow_index: int


@dataclass(frozen=True)
class EnvelopePageItem:
    envelope: Envelope
    target_amount: int
    progress_percentage: int
    filled_segments: int
    status_message: str


@dataclass(frozen=True)
class EnvelopeCreationForm:
    name: str
    target_amount: str
    is_financial_pillow: bool
    errors: dict[str, str]


@dataclass(frozen=True)
class EnvelopeEditForm:
    envelope_id: int
    name: str
    target_amount: str
    errors: dict[str, str]


@dataclass(frozen=True)
class EnvelopeAmountForm:
    envelope_id: int
    operation: Literal["increment", "decrement"]
    amount: str
    is_regular: bool
    error: str


@dataclass(frozen=True)
class SalaryForm:
    value: str
    error: str


@dataclass(frozen=True)
class UsernameForm:
    value: str
    error: str


@dataclass(frozen=True)
class HistoryDay:
    label: str
    transactions: list[Contribution]


@dataclass(frozen=True)
class HistoryEditForm:
    transaction_id: int
    amount: str
    transaction_date: str
    is_regular: bool
    error: str | None = None


@dataclass(frozen=True)
class SpendingForm:
    name: str = ""
    amount: str = ""
    item_id: int | None = None
    item_kind: str = "planned"
    quantity: str = "1"
    error: str | None = None


@dataclass(frozen=True)
class RoutinePageItem:
    routine: RoutineSpending
    is_selected: bool
    quantity: int
    monthly_amount: int


@dataclass(frozen=True)
class RecentSpendingMonth:
    label: str
    purchases: list[ActualSpending]


@dataclass(frozen=True)
class RecentSpendingSummary:
    purchases_count: int
    total_amount: int
    months: list[RecentSpendingMonth]


def _get_envelope_or_404(envelope_id: int) -> Envelope:
    envelope = Envelope.get(envelope_id)
    if envelope is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Envelope not found")
    return envelope


def _set_current_amount(envelope: Envelope, current_amount: int) -> Envelope:
    envelope.current_amount = current_amount
    return envelope.save()


def _calculate_progress_percentage(envelope: Envelope, target_amount: int) -> int:
    return min(round(envelope.current_amount / target_amount * 100), 100)


def _envelope_status(
    envelope: Envelope,
    target_amount: int,
    progress_percentage: int,
) -> str:
    remaining_amount = max(target_amount - envelope.current_amount, 0)
    if remaining_amount == 0:
        return "goal reached ✓"
    if progress_percentage >= 85:
        return "almost safe"
    return f"€{remaining_amount:,} to go"


def _recent_month_keys(today: date) -> list[str]:
    month_keys = []
    year = today.year
    month = today.month
    for _ in range(3):
        month_keys.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return month_keys


def _build_recent_spending_summary(user_id: int, today: date) -> RecentSpendingSummary:
    month_keys = _recent_month_keys(today)
    purchases = ActualSpending.significant_planned_for_months(
        user_id,
        month_keys,
        SIGNIFICANT_SPENDING_THRESHOLD,
    )
    purchases_by_month: dict[str, list[ActualSpending]] = {month_key: [] for month_key in month_keys}
    for purchase in purchases:
        purchases_by_month.setdefault(purchase.month_key, []).append(purchase)
    months = [
        RecentSpendingMonth(
            label=month_name[int(month_key[-2:])].upper(),
            purchases=purchases_by_month[month_key],
        )
        for month_key in month_keys
        if purchases_by_month.get(month_key)
    ]
    return RecentSpendingSummary(
        purchases_count=len(purchases),
        total_amount=sum(purchase.amount for purchase in purchases),
        months=months,
    )


def _render_envelope_page(
    request: Request,
    user: User,
    creation_form: EnvelopeCreationForm | None = None,
    editing_envelope_id: int | None = None,
    edit_form: EnvelopeEditForm | None = None,
    amount_form: EnvelopeAmountForm | None = None,
    salary_form: SalaryForm | None = None,
    username_form: UsernameForm | None = None,
    history_envelope_id: int | None = None,
    history_edit_transaction: Contribution | None = None,
    history_edit_form: HistoryEditForm | None = None,
    spending_form: SpendingForm | None = None,
    status_code: int = status.HTTP_200_OK,
) -> Response:
    envelopes = Envelope.for_user(user.id)
    spending_pool = SpendingPool.for_user(user.id)
    planned_spending = PlannedSpending.for_user(user.id)
    today = date.today()
    current_spending_month = today.strftime("%Y-%m")
    spending_state = monthly_money_state(user.id, current_spending_month)
    recent_spending = _build_recent_spending_summary(user.id, today)
    routine_spending = RoutineSpending.for_user(user.id)
    routine_selections = RoutineSpendingSelection.for_month(
        [routine.id for routine in routine_spending],
        current_spending_month,
    )
    routine_items = [
        RoutinePageItem(
            routine=routine,
            is_selected=routine.id in routine_selections,
            quantity=routine_selections[routine.id].quantity if routine.id in routine_selections else 1,
            monthly_amount=(
                routine.default_amount * routine_selections[routine.id].quantity
                if routine.id in routine_selections
                else routine.default_amount
            ),
        )
        for routine in routine_spending
    ]
    regular_contributions = Contribution.regular_for_user(user.id)
    contributions_by_envelope: dict[int, list[tuple[int, datetime]]] = {}
    for contribution in regular_contributions:
        contributions_by_envelope.setdefault(contribution.envelope_id, []).append(
            (contribution.amount, contribution.contributed_at)
        )
    saving_insight = calculate_saving_insight(
        user.salary,
        (
            (contribution.amount, contribution.contributed_at)
            for contribution in regular_contributions
        ),
    )
    envelope_items = []
    goal_projections = []
    goal_histories: list[GoalHistory] = []
    for envelope in envelopes:
        target_amount = envelope.target_amount
        progress_percentage = _calculate_progress_percentage(envelope, target_amount)
        goal_histories.append(
            GoalHistory(
                envelope_id=envelope.id,
                envelope_name=envelope.name,
                current_amount=envelope.current_amount,
                target_amount=target_amount,
                regular_contributions=tuple(
                    contributions_by_envelope.get(envelope.id, [])
                ),
            )
        )
        goal_projection = calculate_goal_projection(
            envelope_id=envelope.id,
            envelope_name=envelope.name,
            current_amount=envelope.current_amount,
            target_amount=target_amount,
            regular_contributions=contributions_by_envelope.get(envelope.id, []),
        )
        if goal_projection is not None:
            goal_projections.append(goal_projection)
        envelope_items.append(
            EnvelopePageItem(
                envelope=envelope,
                target_amount=target_amount,
                progress_percentage=progress_percentage,
                filled_segments=progress_percentage // 10,
                status_message=_envelope_status(envelope, target_amount, progress_percentage),
            )
        )
    attention_observations = calculate_attention_observations(user.salary, goal_histories)
    history_days: list[HistoryDay] = []
    if history_envelope_id is not None:
        history_transactions = Contribution.newest_first_for_envelope(history_envelope_id)
        grouped_transactions: dict[date, list[Contribution]] = {}
        for transaction in history_transactions:
            transaction_date = transaction.contributed_at.date()
            grouped_transactions.setdefault(transaction_date, []).append(transaction)
        history_days = [
            HistoryDay(
                label=f"{month_name[transaction_date.month].upper()} {transaction_date.day}",
                transactions=transactions,
            )
            for transaction_date, transactions in grouped_transactions.items()
        ]
    return templates.TemplateResponse(
        request,
        "envelope/index.html",
        {
            "user": user,
            "envelope_items": envelope_items,
            "creation_form": creation_form,
            "editing_envelope_id": editing_envelope_id,
            "edit_form": edit_form,
            "amount_form": amount_form,
            "salary_form": salary_form,
            "username_form": username_form,
            "saving_insight": saving_insight,
            "goal_projections": goal_projections,
            "attention_observations": attention_observations,
            "history_envelope_id": history_envelope_id,
            "history_days": history_days,
            "history_edit_transaction": history_edit_transaction,
            "history_edit_form": history_edit_form,
            "spending_pool": spending_pool,
            "spending_state": spending_state,
            "routine_items": routine_items,
            "planned_spending": planned_spending,
            "spending_form": spending_form,
            "current_spending_month": current_spending_month,
            "recent_spending": recent_spending,
            "has_financial_pillow": any(envelope.is_financial_pillow for envelope in envelopes),
            "financial_pillow_target": (
                calculate_financial_pillow_target(
                    user.salary,
                    FINANCIAL_PILLOW_SALARY_MULTIPLIER,
                )
                if user.salary > 0
                else None
            ),
            "financial_pillow_index": FINANCIAL_PILLOW_SALARY_MULTIPLIER,
        },
        status_code=status_code,
    )


@router.patch("/users/{user_id}/salary", response_model=SalaryResponse)
def update_user_salary(user_id: int, payload: SalaryUpdate) -> User:
    user = User.get(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user.update_salary(payload.salary)


@router.post(
    "/users/{user_id}/envelopes",
    response_model=EnvelopeResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_envelope(user_id: int, payload: EnvelopeCreate) -> Envelope:
    if User.get(user_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    try:
        return Envelope.create(user_id=user_id, **payload.model_dump())
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error


@router.get("/users/{user_id}/envelopes", response_model=list[EnvelopeResponse])
def get_user_envelopes(user_id: int) -> list[Envelope]:
    if User.get(user_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return Envelope.for_user(user_id)


@router.patch("/users/{user_id}/envelopes/order", response_model=list[EnvelopeResponse])
def reorder_user_envelopes(user_id: int, payload: EnvelopeOrderUpdate) -> list[Envelope]:
    if User.get(user_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    try:
        return Envelope.reorder_for_user(user_id, payload.envelope_ids)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error


@router.post("/users/{user_id}/spending/amount", response_class=HTMLResponse)
def change_spending_amount(
    request: Request,
    user_id: int,
    operation: Annotated[Literal["increment", "decrement"], Form()],
    amount: Annotated[str, Form()] = "",
) -> Response:
    user = User.get(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    pool = SpendingPool.for_user(user_id)
    try:
        pool.change_amount(int(amount), operation)
    except (ValueError, TypeError) as error:
        return _render_envelope_page(
            request,
            user,
            spending_form=SpendingForm(amount=amount, item_kind="available", error=str(error)),
            status_code=422,
        )
    return RedirectResponse(request.url_for("view_user_envelopes", user_id=user_id), status_code=303)


@router.post("/users/{user_id}/spending/create", response_class=HTMLResponse)
@router.post("/users/{user_id}/spending/planned/create", response_class=HTMLResponse)
def create_planned_spending(
    request: Request,
    user_id: int,
    name: Annotated[str, Form()] = "",
    amount: Annotated[str, Form()] = "",
) -> Response:
    user = User.get(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    normalized_name = name.strip()
    error: str | None = None
    try:
        parsed_amount = int(amount)
        if parsed_amount <= 0:
            error = "Use an amount above 0."
    except (ValueError, TypeError):
        parsed_amount = 0
        error = "Enter a whole amount."
    if not normalized_name:
        error = "Add a name."
    if error:
        return _render_envelope_page(
            request,
            user,
            spending_form=SpendingForm(name=name, amount=amount, item_kind="planned", error=error),
            status_code=422,
        )
    PlannedSpending.create(user_id=user_id, name=normalized_name, amount=parsed_amount)
    return RedirectResponse(request.url_for("view_user_envelopes", user_id=user_id), status_code=303)


@router.post("/users/{user_id}/spending/{item_id}/edit", response_class=HTMLResponse)
def edit_planned_spending(
    request: Request,
    user_id: int,
    item_id: int,
    name: Annotated[str, Form()] = "",
    amount: Annotated[str, Form()] = "",
) -> Response:
    user = User.get(user_id)
    item = PlannedSpending.get(item_id)
    if user is None or item is None or item.user_id != user_id:
        raise HTTPException(status_code=404, detail="Planned spending not found")
    try:
        parsed_amount = int(amount)
        if parsed_amount <= 0:
            raise ValueError("Use an amount above 0.")
        if not name.strip():
            raise ValueError("Add a name.")
        item.name = name.strip()
        item.amount = parsed_amount
        item.save()
    except (ValueError, TypeError) as error:
        return _render_envelope_page(
            request,
            user,
            spending_form=SpendingForm(
                name=name,
                amount=amount,
                item_id=item_id,
                item_kind="planned",
                error=str(error),
            ),
            status_code=422,
        )
    return RedirectResponse(request.url_for("view_user_envelopes", user_id=user_id), status_code=303)


@router.post("/users/{user_id}/spending/{item_id}/delete", response_class=HTMLResponse)
def delete_planned_spending(user_id: int, item_id: int) -> Response:
    user = User.get(user_id)
    item = PlannedSpending.get(item_id)
    if user is None or item is None or item.user_id != user_id:
        raise HTTPException(status_code=404, detail="Planned spending not found")
    item.delete()
    return RedirectResponse(f"/users/{user_id}/envelopes/page", status_code=303)


@router.post("/users/{user_id}/spending/{item_id}/spend", response_class=HTMLResponse)
def spend_planned_spending(
    request: Request,
    user_id: int,
    item_id: int,
) -> Response:
    user = User.get(user_id)
    item = PlannedSpending.get(item_id)
    if user is None or item is None or item.user_id != user_id:
        raise HTTPException(status_code=404, detail="Planned spending not found")
    try:
        spend_planned_item(user_id, item_id, date.today().strftime("%Y-%m"))
    except ValueError as error:
        return _render_envelope_page(
            request,
            user,
            spending_form=SpendingForm(
                item_id=item_id,
                item_kind="planned-spend",
                error=str(error),
            ),
            status_code=422,
        )
    return RedirectResponse(request.url_for("view_user_envelopes", user_id=user_id), status_code=303)


@router.post("/users/{user_id}/spending/routine/create", response_class=HTMLResponse)
def create_routine_spending(
    request: Request,
    user_id: int,
    name: Annotated[str, Form()] = "",
    amount: Annotated[str, Form()] = "",
) -> Response:
    user = User.get(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    normalized_name = name.strip()
    error: str | None = None
    try:
        parsed_amount = int(amount)
        if parsed_amount <= 0:
            error = "Use an amount above 0."
    except (ValueError, TypeError):
        parsed_amount = 0
        error = "Enter a whole amount."
    if not normalized_name:
        error = "Add a name."
    if error:
        return _render_envelope_page(
            request,
            user,
            spending_form=SpendingForm(name=name, amount=amount, item_kind="routine", error=error),
            status_code=422,
        )
    RoutineSpending.create(user_id=user_id, name=normalized_name, default_amount=parsed_amount)
    return RedirectResponse(request.url_for("view_user_envelopes", user_id=user_id), status_code=303)


@router.post("/users/{user_id}/spending/routine/{item_id}/edit", response_class=HTMLResponse)
def edit_routine_spending(
    request: Request,
    user_id: int,
    item_id: int,
    name: Annotated[str, Form()] = "",
    amount: Annotated[str, Form()] = "",
) -> Response:
    user = User.get(user_id)
    item = RoutineSpending.get(item_id)
    if user is None or item is None or item.user_id != user_id:
        raise HTTPException(status_code=404, detail="Routine spending not found")
    try:
        parsed_amount = int(amount)
        if parsed_amount <= 0:
            raise ValueError("Use an amount above 0.")
        if not name.strip():
            raise ValueError("Add a name.")
        item.name = name.strip()
        item.default_amount = parsed_amount
        item.save()
    except (ValueError, TypeError) as error:
        return _render_envelope_page(
            request,
            user,
            spending_form=SpendingForm(
                name=name,
                amount=amount,
                item_id=item_id,
                item_kind="routine",
                error=str(error),
            ),
            status_code=422,
        )
    return RedirectResponse(request.url_for("view_user_envelopes", user_id=user_id), status_code=303)


@router.post("/users/{user_id}/spending/routine/{item_id}/delete", response_class=HTMLResponse)
def delete_routine_spending(user_id: int, item_id: int) -> Response:
    user = User.get(user_id)
    item = RoutineSpending.get(item_id)
    if user is None or item is None or item.user_id != user_id:
        raise HTTPException(status_code=404, detail="Routine spending not found")
    item.delete()
    return RedirectResponse(f"/users/{user_id}/envelopes/page", status_code=303)


@router.post("/users/{user_id}/spending/routine/{item_id}/spend", response_class=HTMLResponse)
def spend_routine_spending(
    request: Request,
    user_id: int,
    item_id: int,
) -> Response:
    user = User.get(user_id)
    item = RoutineSpending.get(item_id)
    if user is None or item is None or item.user_id != user_id:
        raise HTTPException(status_code=404, detail="Routine spending not found")
    try:
        spend_routine_for_month(user_id, item_id, date.today().strftime("%Y-%m"))
    except ValueError as error:
        return _render_envelope_page(
            request,
            user,
            spending_form=SpendingForm(
                item_id=item_id,
                item_kind="routine-spend",
                error=str(error),
            ),
            status_code=422,
        )
    return RedirectResponse(request.url_for("view_user_envelopes", user_id=user_id), status_code=303)


@router.post("/users/{user_id}/spending/routine/{item_id}/selection", response_class=HTMLResponse)
def update_routine_spending_selection(
    request: Request,
    user_id: int,
    item_id: int,
    selected: Annotated[str | None, Form()] = None,
    quantity: Annotated[str, Form()] = "1",
) -> Response:
    user = User.get(user_id)
    item = RoutineSpending.get(item_id)
    if user is None or item is None or item.user_id != user_id:
        raise HTTPException(status_code=404, detail="Routine spending not found")
    month_key = date.today().strftime("%Y-%m")
    try:
        parsed_quantity = int(quantity)
        selections = RoutineSpendingSelection.for_month([item_id], month_key)
        previous_amount = (
            item.default_amount * selections[item_id].quantity
            if item_id in selections
            else 0
        )
        next_amount = item.default_amount * parsed_quantity if selected else 0
        spending_state = monthly_money_state(user_id, month_key)
        if next_amount > spending_state.free + previous_amount:
            raise ValueError("Not enough free money.")
        RoutineSpendingSelection.set_for_month(
            routine_id=item_id,
            month_key=month_key,
            quantity=parsed_quantity if selected else None,
        )
    except (ValueError, TypeError) as error:
        return _render_envelope_page(
            request,
            user,
            spending_form=SpendingForm(
                item_id=item_id,
                item_kind="routine-selection",
                quantity=quantity,
                error=str(error),
            ),
            status_code=422,
        )
    return RedirectResponse(request.url_for("view_user_envelopes", user_id=user_id), status_code=303)


@router.get("/envelopes/{envelope_id}", response_model=EnvelopeResponse)
def get_envelope(envelope_id: int) -> Envelope:
    return _get_envelope_or_404(envelope_id)


@router.patch("/envelopes/{envelope_id}/current-amount", response_model=EnvelopeResponse)
def update_current_amount(envelope_id: int, payload: EnvelopeCurrentAmountUpdate) -> Envelope:
    envelope = _get_envelope_or_404(envelope_id)
    return _set_current_amount(envelope, payload.current_amount)


@router.patch("/envelopes/{envelope_id}", response_model=EnvelopeResponse)
def update_envelope_configuration(
    envelope_id: int,
    payload: EnvelopeConfigurationUpdate,
) -> Envelope:
    envelope = _get_envelope_or_404(envelope_id)
    try:
        return envelope.update_configuration(
            name=payload.name,
            target_amount=payload.target_amount,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error


@router.delete("/envelopes/{envelope_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_envelope(envelope_id: int) -> None:
    envelope = _get_envelope_or_404(envelope_id)
    envelope.delete()


@router.get(
    "/users/{user_id}/envelopes/page",
    response_class=HTMLResponse,
    name="view_user_envelopes",
)
def view_user_envelopes(
    request: Request,
    user_id: int,
    edit_envelope_id: int | None = None,
    history_envelope_id: int | None = None,
    edit_transaction_id: int | None = None,
) -> Response:
    user = User.get(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if edit_envelope_id is not None:
        envelope = _get_envelope_or_404(edit_envelope_id)
        if envelope.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Envelope not found")

    history_edit_transaction: Contribution | None = None
    history_edit_form: HistoryEditForm | None = None
    if history_envelope_id is not None:
        history_envelope = _get_envelope_or_404(history_envelope_id)
        if history_envelope.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Envelope not found")
        if edit_transaction_id is not None:
            transaction = Contribution.get(edit_transaction_id)
            if transaction is None or transaction.envelope_id != history_envelope_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
            history_edit_transaction = transaction
            history_edit_form = HistoryEditForm(
                transaction_id=transaction.id,
                amount=str(transaction.amount),
                transaction_date=transaction.contributed_at.date().isoformat(),
                is_regular=transaction.is_regular,
            )

    return _render_envelope_page(
        request,
        user,
        editing_envelope_id=edit_envelope_id,
        history_envelope_id=history_envelope_id,
        history_edit_transaction=history_edit_transaction,
        history_edit_form=history_edit_form,
    )


@router.post(
    "/users/{user_id}/envelopes/create",
    response_class=HTMLResponse,
    name="create_envelope_from_page",
)
def create_envelope_from_page(
    request: Request,
    user_id: int,
    name: Annotated[str, Form()] = "",
    target_amount: Annotated[str, Form()] = "",
    financial_pillow: Annotated[str | None, Form()] = None,
) -> Response:
    user = User.get(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    normalized_name = name.strip()
    is_financial_pillow = financial_pillow == EnvelopeKind.FINANCIAL_PILLOW
    existing_envelopes = Envelope.for_user(user_id)
    errors: dict[str, str] = {}
    if not normalized_name:
        errors["name"] = "Add a name."
    elif len(normalized_name) > 255:
        errors["name"] = "Keep the name under 255 characters."

    parsed_target_amount: int | None = None
    if is_financial_pillow:
        if any(envelope.is_financial_pillow for envelope in existing_envelopes):
            errors["financial_pillow"] = "You already have a financial pillow."
        try:
            calculate_financial_pillow_target(user.salary)
        except ValueError as error:
            errors["financial_pillow"] = str(error)
    else:
        try:
            parsed_target_amount = int(target_amount)
        except ValueError:
            errors["target_amount"] = "Enter a whole amount."
        else:
            if parsed_target_amount <= 0:
                errors["target_amount"] = "Use an amount above 0."

    if errors:
        creation_form = EnvelopeCreationForm(
            name=name,
            target_amount=target_amount,
            is_financial_pillow=is_financial_pillow,
            errors=errors,
        )
        return _render_envelope_page(
            request,
            user,
            creation_form=creation_form,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )

    next_priority = max((envelope.priority for envelope in existing_envelopes), default=0) + 1
    try:
        Envelope.create(
            user_id=user_id,
            name=normalized_name,
            target_amount=parsed_target_amount,
            priority=next_priority,
            kind=(
                EnvelopeKind.FINANCIAL_PILLOW
                if is_financial_pillow
                else EnvelopeKind.REGULAR
            ),
        )
    except ValueError as error:
        creation_form = EnvelopeCreationForm(
            name=name,
            target_amount=target_amount,
            is_financial_pillow=is_financial_pillow,
            errors={"financial_pillow": str(error)},
        )
        return _render_envelope_page(
            request,
            user,
            creation_form=creation_form,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    return RedirectResponse(
        request.url_for("view_user_envelopes", user_id=user_id),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post(
    "/users/{user_id}/salary/edit",
    response_class=HTMLResponse,
    name="edit_salary_from_page",
)
def edit_salary_from_page(
    request: Request,
    user_id: int,
    salary: Annotated[str, Form()] = "",
) -> Response:
    user = User.get(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    error_message: str | None = None
    try:
        parsed_salary = int(salary)
    except ValueError:
        error_message = "Enter a whole amount."
    else:
        if parsed_salary <= 0:
            error_message = "Use an amount above 0."

    if error_message is not None:
        return _render_envelope_page(
            request,
            user,
            salary_form=SalaryForm(value=salary, error=error_message),
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )

    user.update_salary(parsed_salary)
    return RedirectResponse(
        request.url_for("view_user_envelopes", user_id=user_id),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post(
    "/users/{user_id}/username/edit",
    response_class=HTMLResponse,
    name="edit_username_from_page",
)
def edit_username_from_page(
    request: Request,
    user_id: int,
    username: Annotated[str, Form()] = "",
) -> Response:
    user = User.get(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    try:
        user.update_username(username)
    except ValueError as error:
        return _render_envelope_page(
            request,
            user,
            username_form=UsernameForm(value=username, error=str(error)),
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    return RedirectResponse(
        request.url_for("view_user_envelopes", user_id=user_id),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post(
    "/users/{user_id}/envelopes/{envelope_id}/edit",
    response_class=HTMLResponse,
    name="edit_envelope_from_page",
)
def edit_envelope_from_page(
    request: Request,
    user_id: int,
    envelope_id: int,
    name: Annotated[str, Form()] = "",
    target_amount: Annotated[str | None, Form()] = None,
) -> Response:
    user = User.get(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    envelope = _get_envelope_or_404(envelope_id)
    if envelope.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Envelope not found")

    normalized_name = name.strip()
    errors: dict[str, str] = {}
    if not normalized_name:
        errors["name"] = "Add a name."
    elif len(normalized_name) > 255:
        errors["name"] = "Keep the name under 255 characters."

    parsed_target_amount: int | None = None
    if envelope.is_financial_pillow:
        if target_amount is not None:
            errors["target_amount"] = "The calculated goal cannot be changed."
    else:
        try:
            parsed_target_amount = int(target_amount or "")
        except ValueError:
            errors["target_amount"] = "Enter a whole amount."
        else:
            if parsed_target_amount <= 0:
                errors["target_amount"] = "Use an amount above 0."

    if not errors:
        try:
            envelope.update_configuration(
                name=normalized_name,
                target_amount=parsed_target_amount,
            )
        except ValueError as error:
            errors["target_amount"] = str(error)

    if errors:
        edit_form = EnvelopeEditForm(
            envelope_id=envelope_id,
            name=name,
            target_amount=target_amount or "",
            errors=errors,
        )
        return _render_envelope_page(
            request,
            user,
            editing_envelope_id=envelope_id,
            edit_form=edit_form,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )

    return RedirectResponse(
        request.url_for("view_user_envelopes", user_id=user_id),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post(
    "/users/{user_id}/envelopes/{envelope_id}/amount",
    response_class=HTMLResponse,
    name="change_envelope_amount",
)
def change_envelope_amount(
    request: Request,
    user_id: int,
    envelope_id: int,
    operation: Annotated[Literal["increment", "decrement"], Form()],
    amount: Annotated[str, Form()] = "",
    regular_contribution: Annotated[bool, Form()] = True,
) -> Response:
    user = User.get(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    envelope = _get_envelope_or_404(envelope_id)
    if envelope.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Envelope not found")

    error_message: str | None = None
    try:
        parsed_amount = int(amount)
    except ValueError:
        error_message = "Enter a whole amount."
    else:
        if parsed_amount <= 0:
            error_message = "Use an amount above 0."
        elif operation == "increment":
            try:
                Contribution.add_to_envelope(
                    envelope_id=envelope.id,
                    amount=parsed_amount,
                    is_regular=regular_contribution,
                )
            except ValueError as error:
                error_message = str(error)
        else:
            try:
                Contribution.withdraw_from_envelope(envelope.id, parsed_amount)
            except ValueError as error:
                error_message = str(error)

    if error_message is not None:
        return _render_envelope_page(
            request,
            user,
            amount_form=EnvelopeAmountForm(
                envelope_id=envelope_id,
                operation=operation,
                amount=amount,
                is_regular=regular_contribution,
                error=error_message,
            ),
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )

    return RedirectResponse(
        request.url_for("view_user_envelopes", user_id=user_id),
        status_code=status.HTTP_303_SEE_OTHER,
    )


def _history_page_url(request: Request, user_id: int, envelope_id: int) -> str:
    return f"{request.url_for('view_user_envelopes', user_id=user_id)}?history_envelope_id={envelope_id}"


@router.post(
    "/users/{user_id}/envelopes/{envelope_id}/history/{transaction_id}/edit",
    response_class=HTMLResponse,
    name="edit_transaction_from_page",
)
def edit_transaction_from_page(
    request: Request,
    user_id: int,
    envelope_id: int,
    transaction_id: int,
    amount: Annotated[str, Form()] = "",
    transaction_date: Annotated[str, Form()] = "",
    regular_contribution: Annotated[bool, Form()] = False,
) -> Response:
    user = User.get(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    envelope = _get_envelope_or_404(envelope_id)
    if envelope.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Envelope not found")
    transaction = Contribution.get(transaction_id)
    if transaction is None or transaction.envelope_id != envelope_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")

    error_message: str | None = None
    try:
        parsed_amount = int(amount)
    except ValueError:
        error_message = "Enter a whole amount."
    else:
        if parsed_amount <= 0:
            error_message = "Use an amount above 0."

    parsed_date: datetime | None = None
    try:
        parsed_date = datetime.strptime(transaction_date, "%Y-%m-%d").replace(hour=12)
    except ValueError:
        if error_message is None:
            error_message = "Choose a valid date."

    if error_message is None and parsed_date is not None:
        try:
            transaction.update_transaction(
                amount=parsed_amount,
                contributed_at=parsed_date,
                is_regular=regular_contribution,
            )
        except ValueError as error:
            error_message = str(error)

    if error_message is not None:
        return _render_envelope_page(
            request,
            user,
            history_envelope_id=envelope_id,
            history_edit_transaction=transaction,
            history_edit_form=HistoryEditForm(
                transaction_id=transaction_id,
                amount=amount,
                transaction_date=transaction_date,
                is_regular=regular_contribution,
                error=error_message,
            ),
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )

    return RedirectResponse(
        _history_page_url(request, user_id, envelope_id),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post(
    "/users/{user_id}/envelopes/{envelope_id}/history/{transaction_id}/delete",
    response_class=HTMLResponse,
    name="delete_transaction_from_page",
)
def delete_transaction_from_page(
    request: Request,
    user_id: int,
    envelope_id: int,
    transaction_id: int,
) -> Response:
    user = User.get(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    envelope = _get_envelope_or_404(envelope_id)
    if envelope.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Envelope not found")
    transaction = Contribution.get(transaction_id)
    if transaction is None or transaction.envelope_id != envelope_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")

    try:
        transaction.delete_transaction()
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error

    return RedirectResponse(
        _history_page_url(request, user_id, envelope_id),
        status_code=status.HTTP_303_SEE_OTHER,
    )
