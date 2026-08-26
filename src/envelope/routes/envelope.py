from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.envelope.service import calculate_financial_pillow_target
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


class EnvelopeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    name: str
    current_amount: int
    target_amount: int
    priority: int
    kind: EnvelopeKind


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
            "has_financial_pillow": any(envelope.is_financial_pillow for envelope in envelopes),
            "financial_pillow_target": (
                calculate_financial_pillow_target(user.salary) if user.salary > 0 else None
            ),
        },
        status_code=status_code,
    )


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


@router.delete("/envelopes/{envelope_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_envelope(envelope_id: int) -> None:
    envelope = _get_envelope_or_404(envelope_id)
    envelope.delete()


@router.get(
    "/users/{user_id}/envelopes/page",
    response_class=HTMLResponse,
    name="view_user_envelopes",
)
def view_user_envelopes(request: Request, user_id: int) -> Response:
    user = User.get(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return _render_envelope_page(request, user)


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
    "/users/{user_id}/envelopes/{envelope_id}/amount",
    response_class=RedirectResponse,
    name="change_envelope_amount",
)
def change_envelope_amount(
    request: Request,
    user_id: int,
    envelope_id: int,
    amount: Annotated[int, Form(gt=0)],
    operation: Annotated[Literal["increment", "decrement"], Form()],
) -> RedirectResponse:
    envelope = _get_envelope_or_404(envelope_id)
    if envelope.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Envelope not found")

    delta = amount if operation == "increment" else -amount
    try:
        _set_current_amount(envelope, envelope.current_amount + delta)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error))

    return RedirectResponse(
        request.url_for("view_user_envelopes", user_id=user_id),
        status_code=status.HTTP_303_SEE_OTHER,
    )
