"""Pydantic v2 schemas for the customer-management API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

CustomerStatus = Literal["active", "archived"]
ContactKind = Literal["phone", "email", "address", "other"]
InteractionKind = Literal["call", "email", "meeting", "chat", "other"]

NonEmptyStr = Annotated[str, Field(min_length=1)]

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int


class ListQuery(BaseModel):
    """Query params for the customer list; invalid values yield 422."""

    q: str | None = None
    status: CustomerStatus | None = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


# --------------------------------------------------------------------------- #
# Customer
# --------------------------------------------------------------------------- #
class CustomerBase(BaseModel):
    display_name: NonEmptyStr
    company: str | None = None


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    display_name: NonEmptyStr | None = None
    company: str | None = None
    status: CustomerStatus | None = None


class CustomerRead(CustomerBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: CustomerStatus
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CustomerDetailRead(CustomerRead):
    """Customer plus eagerly loaded contacts (detail endpoint only)."""

    contacts: list[ContactDetailRead] = []


# --------------------------------------------------------------------------- #
# Contact details
# --------------------------------------------------------------------------- #
class ContactDetailBase(BaseModel):
    kind: ContactKind
    value: NonEmptyStr
    label: str | None = None
    is_primary: bool = False


class ContactDetailCreate(ContactDetailBase):
    pass


class ContactDetailUpdate(BaseModel):
    kind: ContactKind | None = None
    value: NonEmptyStr | None = None
    label: str | None = None
    is_primary: bool | None = None


class ContactDetailRead(ContactDetailBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: uuid.UUID
    created_at: datetime


# --------------------------------------------------------------------------- #
# Interactions
# --------------------------------------------------------------------------- #
class InteractionBase(BaseModel):
    kind: InteractionKind
    subject: str | None = None
    body: str = ""
    occurred_at: datetime
    author: str | None = None


class InteractionCreate(InteractionBase):
    pass


class InteractionUpdate(BaseModel):
    kind: InteractionKind | None = None
    subject: str | None = None
    body: str | None = None
    occurred_at: datetime | None = None
    author: str | None = None


class InteractionRead(InteractionBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: uuid.UUID
    created_at: datetime


# --------------------------------------------------------------------------- #
# Notes
# --------------------------------------------------------------------------- #
class NoteBase(BaseModel):
    body: NonEmptyStr


class NoteCreate(NoteBase):
    pass


class NoteUpdate(BaseModel):
    body: NonEmptyStr | None = None


class NoteRead(NoteBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------- #
# Attachments
# --------------------------------------------------------------------------- #
class AttachmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: uuid.UUID
    note_id: uuid.UUID | None
    filename: str
    content_type: str
    size_bytes: int
    created_at: datetime


CustomerDetailRead.model_rebuild()
