from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from src.orm.envelope import Envelope
from src.orm.user import User
from src.template import templates

router = APIRouter(tags=["envelopes"])


class EnvelopeCreate(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=255)]
    current_amount: Annotated[int, Field(ge=0)] = 0
    target_amount: Annotated[int, Field(gt=0)]
    priority: Annotated[int, Field(gt=0)]


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


@dataclass(frozen=True)
class EnvelopePageItem:
    envelope: Envelope
    progress_percentage: int
    filled_segments: int
    status_message: str


def _get_envelope_or_404(envelope_id: int) -> Envelope:
    envelope = Envelope.get(envelope_id)
    if envelope is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Envelope not found")
    return envelope


def _set_current_amount(envelope: Envelope, current_amount: int) -> Envelope:
    envelope.current_amount = current_amount
    return envelope.save()


def _calculate_progress_percentage(envelope: Envelope) -> int:
    return min(round(envelope.current_amount / envelope.target_amount * 100), 100)


def _envelope_status(envelope: Envelope, progress_percentage: int) -> str:
    remaining_amount = max(envelope.target_amount - envelope.current_amount, 0)
    if remaining_amount == 0:
        return "goal reached ✓"
    if progress_percentage >= 85:
        return "almost safe"
    return f"€{remaining_amount:,} to go"


@router.post(
    "/users/{user_id}/envelopes",
    response_model=EnvelopeResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_envelope(user_id: int, payload: EnvelopeCreate) -> Envelope:
    if User.get(user_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return Envelope.create(user_id=user_id, **payload.model_dump())


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

    envelope_items = []
    for envelope in Envelope.for_user(user_id):
        progress_percentage = _calculate_progress_percentage(envelope)
        envelope_items.append(
            EnvelopePageItem(
                envelope=envelope,
                progress_percentage=progress_percentage,
                filled_segments=progress_percentage // 10,
                status_message=_envelope_status(envelope, progress_percentage),
            )
        )
    return templates.TemplateResponse(
        request,
        "envelope/index.html",
        {"user": user, "envelope_items": envelope_items},
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
