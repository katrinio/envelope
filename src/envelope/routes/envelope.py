from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.envelope.service import (
    FINANCIAL_PILLOW_SALARY_MULTIPLIER,
    calculate_financial_pillow_target,
)
from src.orm.contribution import Contribution
from src.orm.envelope import Envelope, EnvelopeKind
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


def _render_envelope_page(
    request: Request,
    user: User,
    creation_form: EnvelopeCreationForm | None = None,
    editing_envelope_id: int | None = None,
    edit_form: EnvelopeEditForm | None = None,
    amount_form: EnvelopeAmountForm | None = None,
    salary_form: SalaryForm | None = None,
    status_code: int = status.HTTP_200_OK,
) -> Response:
    envelopes = Envelope.for_user(user.id)
    envelope_items = []
    for envelope in envelopes:
        target_amount = envelope.target_amount
        progress_percentage = _calculate_progress_percentage(envelope, target_amount)
        envelope_items.append(
            EnvelopePageItem(
                envelope=envelope,
                target_amount=target_amount,
                progress_percentage=progress_percentage,
                filled_segments=progress_percentage // 10,
                status_message=_envelope_status(envelope, target_amount, progress_percentage),
            )
        )
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
) -> Response:
    user = User.get(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if edit_envelope_id is not None:
        envelope = _get_envelope_or_404(edit_envelope_id)
        if envelope.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Envelope not found")

    return _render_envelope_page(
        request,
        user,
        editing_envelope_id=edit_envelope_id,
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
            Contribution.add_to_envelope(
                envelope_id=envelope.id,
                amount=parsed_amount,
                is_regular=regular_contribution,
            )
        else:
            try:
                _set_current_amount(envelope, envelope.current_amount - parsed_amount)
            except ValueError:
                error_message = "Saved amount cannot go below €0."

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
