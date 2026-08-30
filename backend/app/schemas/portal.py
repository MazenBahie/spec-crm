"""Pydantic v2 schemas for the customer-portal API.

``EmailStr`` is not used here: this project pins plain ``pydantic`` (no
``email-validator`` extra, see ``backend/requirements.txt``), so email fields
use ``NonEmptyStr`` plus a light structural check instead of pulling in a new
dependency for this alone.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.customer import NonEmptyStr


def _validate_email(value: str) -> str:
    value = value.strip()
    if "@" not in value or value.startswith("@") or value.endswith("@"):
        raise ValueError("not a valid email address")
    return value.lower()


class PortalSignup(BaseModel):
    email: NonEmptyStr
    # Not `NonEmptyStr` -- combining that Annotated Field(min_length=1) with a
    # second Field(min_length=8) here does not reliably raise the stricter
    # bound, so this field states its own constraint directly.
    password: str = Field(min_length=8)
    display_name: NonEmptyStr

    _normalize_email = field_validator("email")(_validate_email)


class PortalLogin(BaseModel):
    email: NonEmptyStr
    password: NonEmptyStr

    _normalize_email = field_validator("email")(_validate_email)


class PortalUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: uuid.UUID
    email: str
    display_name: str


class PortalAuthResponse(BaseModel):
    token: str
    expires_at: datetime
    portal_user: PortalUserRead


class PortalTicketCreate(BaseModel):
    """No ``customer_id``, ``assignee_id``, or ``priority`` -- all three are
    either derived from the authenticated session or left to staff triage."""

    subject: NonEmptyStr
    description: str = ""
    category_id: uuid.UUID | None = None


class TicketFeedbackCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str | None = None


class TicketFeedbackRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_id: uuid.UUID
    rating: int
    comment: str | None
    created_at: datetime
    updated_at: datetime
