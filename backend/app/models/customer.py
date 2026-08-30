"""Customer-management ORM models.

Every child table cascades from ``customers.id``: deleting a customer removes
its contacts, interactions, notes, and attachment rows. Archiving a customer is
a *soft* state change (``status='archived'`` + ``archived_at``) and deletes
nothing — only ``DELETE /customers/{id}`` cascades.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.portal import PortalUser
    from app.models.ticket import Ticket

CUSTOMER_STATUSES = ("active", "archived")
CONTACT_KINDS = ("phone", "email", "address", "other")
INTERACTION_KINDS = ("call", "email", "meeting", "chat", "other")

customer_status_enum = Enum(*CUSTOMER_STATUSES, name="customer_status")
contact_kind_enum = Enum(*CONTACT_KINDS, name="contact_kind")
interaction_kind_enum = Enum(*INTERACTION_KINDS, name="interaction_kind")


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[uuid.UUID] = _pk()
    display_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    company: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(
        customer_status_enum, nullable=False, server_default="active"
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    contacts: Mapped[list[ContactDetail]] = relationship(
        back_populates="customer",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ContactDetail.kind",
    )
    interactions: Mapped[list[Interaction]] = relationship(
        back_populates="customer", cascade="all, delete-orphan", passive_deletes=True
    )
    notes: Mapped[list[Note]] = relationship(
        back_populates="customer", cascade="all, delete-orphan", passive_deletes=True
    )
    attachments: Mapped[list[Attachment]] = relationship(
        back_populates="customer", cascade="all, delete-orphan", passive_deletes=True
    )
    tickets: Mapped[list[Ticket]] = relationship(
        back_populates="customer", cascade="all, delete-orphan", passive_deletes=True
    )
    portal_users: Mapped[list[PortalUser]] = relationship(
        back_populates="customer", cascade="all, delete-orphan", passive_deletes=True
    )

    @property
    def is_archived(self) -> bool:
        return self.status == "archived"


class ContactDetail(Base):
    __tablename__ = "contact_details"
    __table_args__ = (
        # A customer may hold many contacts of one kind but at most one primary
        # per kind. Enforced by a PARTIAL unique index — Postgres (and SQLite
        # 3.8+) only; a plain unique index here would forbid the second
        # non-primary contact too.
        Index(
            "uq_contact_primary_per_kind",
            "customer_id",
            "kind",
            unique=True,
            postgresql_where=text("is_primary"),
            sqlite_where=text("is_primary"),
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    customer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(contact_kind_enum, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str | None] = mapped_column(String(64))
    is_primary: Mapped[bool] = mapped_column(
        nullable=False, default=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    customer: Mapped[Customer] = relationship(back_populates="contacts")


class Interaction(Base):
    __tablename__ = "interactions"
    __table_args__ = (
        Index("ix_interactions_customer_occurred", "customer_id", text("occurred_at DESC")),
    )

    id: Mapped[uuid.UUID] = _pk()
    customer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(interaction_kind_enum, nullable=False)
    subject: Mapped[str | None] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    author: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    customer: Mapped[Customer] = relationship(back_populates="interactions")


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[uuid.UUID] = _pk()
    customer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    customer: Mapped[Customer] = relationship(back_populates="notes")
    attachments: Mapped[list[Attachment]] = relationship(
        back_populates="note", passive_deletes=True
    )


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[uuid.UUID] = _pk()
    customer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Nullable so a file can hang off the customer directly rather than a note.
    note_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("notes.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    customer: Mapped[Customer] = relationship(back_populates="attachments")
    note: Mapped[Note | None] = relationship(back_populates="attachments")
