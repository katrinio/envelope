from typing import Annotated

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from src.orm.envelope import Envelope
from src.orm.user import User

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


def _get_envelope_or_404(envelope_id: int) -> Envelope:
    envelope = Envelope.get(envelope_id)
    if envelope is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Envelope not found")
    return envelope


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
    envelope.current_amount = payload.current_amount
    return envelope.save()


@router.delete("/envelopes/{envelope_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_envelope(envelope_id: int) -> None:
    envelope = _get_envelope_or_404(envelope_id)
    envelope.delete()
