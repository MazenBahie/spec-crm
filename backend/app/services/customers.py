"""Customer-management service layer.

Pure functions over a SQLAlchemy ``Session`` -- no FastAPI imports. Callers own
the transaction boundary (the ``get_db`` dependency commits on success); these
functions ``flush`` so generated ids and server defaults are readable, but never
commit.

Concurrency: every update is last-write-wins. Optimistic locking is out of
scope, so two overlapping PATCHes silently keep the later one.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import BinaryIO

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.customer import Attachment, ContactDetail, Customer, Interaction, Note
from app.schemas.customer import (
    ContactDetailCreate,
    ContactDetailUpdate,
    CustomerCreate,
    CustomerUpdate,
    InteractionCreate,
    InteractionUpdate,
    NoteCreate,
    NoteUpdate,
)
from app.services.errors import Conflict, NotFound
from app.services.storage import Storage


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Customers
# --------------------------------------------------------------------------- #
def list_customers(
    db: Session,
    *,
    q: str | None = None,
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Customer], int]:
    """Return one page of customers plus the total matching the filters."""
    filters = []
    if q and q.strip():
        pattern = f"%{q.strip().lower()}%"
        filters.append(
            or_(
                func.lower(Customer.display_name).like(pattern),
                func.lower(func.coalesce(Customer.company, "")).like(pattern),
            )
        )
    if status:
        filters.append(Customer.status == status)

    total = db.scalar(select(func.count()).select_from(Customer).where(*filters)) or 0
    rows = db.scalars(
        select(Customer)
        .where(*filters)
        .order_by(Customer.display_name.asc(), Customer.id.asc())
        .limit(limit)
        .offset(offset)
    ).all()
    return list(rows), total


def get_customer(
    db: Session, customer_id: uuid.UUID, *, with_contacts: bool = False
) -> Customer:
    stmt = select(Customer).where(Customer.id == customer_id)
    if with_contacts:
        stmt = stmt.options(selectinload(Customer.contacts))
    customer = db.scalars(stmt).first()
    if customer is None:
        raise NotFound(f"customer {customer_id} not found")
    return customer


def create_customer(db: Session, payload: CustomerCreate) -> Customer:
    customer = Customer(display_name=payload.display_name, company=payload.company)
    db.add(customer)
    db.flush()
    db.refresh(customer)
    return customer


def update_customer(
    db: Session, customer_id: uuid.UUID, payload: CustomerUpdate
) -> Customer:
    """Partial update. Allowed even while archived (last-write-wins)."""
    customer = get_customer(db, customer_id)
    data = payload.model_dump(exclude_unset=True)

    if data.get("status") is not None:
        customer.archived_at = _now() if data["status"] == "archived" else None
    for field, value in data.items():
        setattr(customer, field, value)

    db.flush()
    db.refresh(customer)
    return customer


def archive_customer(db: Session, customer_id: uuid.UUID) -> Customer:
    """Soft-archive. Idempotent, and deletes nothing."""
    customer = get_customer(db, customer_id)
    customer.status = "archived"
    customer.archived_at = customer.archived_at or _now()
    db.flush()
    db.refresh(customer)
    return customer


def delete_customer(
    db: Session, customer_id: uuid.UUID, *, storage: Storage | None = None
) -> None:
    """Hard delete. Children cascade; attachment files are removed best-effort."""
    customer = get_customer(db, customer_id)
    paths = list(
        db.scalars(
            select(Attachment.storage_path).where(Attachment.customer_id == customer_id)
        )
    )
    db.delete(customer)
    db.flush()
    if storage is not None:
        _delete_files(storage, paths)


def _delete_files(storage: Storage, paths: Iterable[str]) -> None:
    """Remove files without letting one failure abort the caller."""
    for path in paths:
        storage.delete(path)


def _require_active(customer: Customer) -> None:
    if customer.is_archived:
        raise Conflict("customer is archived")


# --------------------------------------------------------------------------- #
# Contact details
# --------------------------------------------------------------------------- #
def list_contacts(db: Session, customer_id: uuid.UUID) -> list[ContactDetail]:
    get_customer(db, customer_id)
    return list(
        db.scalars(
            select(ContactDetail)
            .where(ContactDetail.customer_id == customer_id)
            .order_by(ContactDetail.kind.asc(), ContactDetail.is_primary.desc())
        )
    )


def _assert_primary_free(
    db: Session,
    customer_id: uuid.UUID,
    kind: str,
    *,
    exclude: uuid.UUID | None = None,
) -> None:
    """Pre-check the single-primary-per-kind rule ahead of the partial index."""
    stmt = (
        select(func.count())
        .select_from(ContactDetail)
        .where(
            ContactDetail.customer_id == customer_id,
            ContactDetail.kind == kind,
            ContactDetail.is_primary.is_(True),
        )
    )
    if exclude is not None:
        stmt = stmt.where(ContactDetail.id != exclude)
    if (db.scalar(stmt) or 0) > 0:
        raise Conflict(f"a primary {kind} contact already exists for this customer")


def get_contact(
    db: Session, customer_id: uuid.UUID, contact_id: uuid.UUID
) -> ContactDetail:
    contact = db.scalars(
        select(ContactDetail).where(
            ContactDetail.id == contact_id, ContactDetail.customer_id == customer_id
        )
    ).first()
    if contact is None:
        raise NotFound(f"contact {contact_id} not found")
    return contact


def create_contact(
    db: Session, customer_id: uuid.UUID, payload: ContactDetailCreate
) -> ContactDetail:
    get_customer(db, customer_id)
    if payload.is_primary:
        _assert_primary_free(db, customer_id, payload.kind)
    contact = ContactDetail(customer_id=customer_id, **payload.model_dump())
    db.add(contact)
    db.flush()
    db.refresh(contact)
    return contact


def update_contact(
    db: Session,
    customer_id: uuid.UUID,
    contact_id: uuid.UUID,
    payload: ContactDetailUpdate,
) -> ContactDetail:
    contact = get_contact(db, customer_id, contact_id)
    data = payload.model_dump(exclude_unset=True)
    kind = data.get("kind") or contact.kind
    if data.get("is_primary", contact.is_primary):
        _assert_primary_free(db, customer_id, kind, exclude=contact_id)
    for field, value in data.items():
        setattr(contact, field, value)
    db.flush()
    db.refresh(contact)
    return contact


def delete_contact(
    db: Session, customer_id: uuid.UUID, contact_id: uuid.UUID
) -> None:
    db.delete(get_contact(db, customer_id, contact_id))
    db.flush()


# --------------------------------------------------------------------------- #
# Interactions
# --------------------------------------------------------------------------- #
def list_interactions(
    db: Session, customer_id: uuid.UUID, *, limit: int = 50, offset: int = 0
) -> tuple[list[Interaction], int]:
    get_customer(db, customer_id)
    where = (Interaction.customer_id == customer_id,)
    total = db.scalar(select(func.count()).select_from(Interaction).where(*where)) or 0
    rows = db.scalars(
        select(Interaction)
        .where(*where)
        .order_by(Interaction.occurred_at.desc(), Interaction.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return list(rows), total


def get_interaction(db: Session, interaction_id: uuid.UUID) -> Interaction:
    interaction = db.get(Interaction, interaction_id)
    if interaction is None:
        raise NotFound(f"interaction {interaction_id} not found")
    return interaction


def create_interaction(
    db: Session, customer_id: uuid.UUID, payload: InteractionCreate
) -> Interaction:
    _require_active(get_customer(db, customer_id))
    interaction = Interaction(customer_id=customer_id, **payload.model_dump())
    db.add(interaction)
    db.flush()
    db.refresh(interaction)
    return interaction


def update_interaction(
    db: Session, interaction_id: uuid.UUID, payload: InteractionUpdate
) -> Interaction:
    interaction = get_interaction(db, interaction_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(interaction, field, value)
    db.flush()
    db.refresh(interaction)
    return interaction


def delete_interaction(db: Session, interaction_id: uuid.UUID) -> None:
    db.delete(get_interaction(db, interaction_id))
    db.flush()


# --------------------------------------------------------------------------- #
# Notes
# --------------------------------------------------------------------------- #
def list_notes(db: Session, customer_id: uuid.UUID) -> list[Note]:
    get_customer(db, customer_id)
    return list(
        db.scalars(
            select(Note)
            .where(Note.customer_id == customer_id)
            .order_by(Note.created_at.desc(), Note.id.desc())
        )
    )


def get_note(db: Session, note_id: uuid.UUID) -> Note:
    note = db.get(Note, note_id)
    if note is None:
        raise NotFound(f"note {note_id} not found")
    return note


def create_note(db: Session, customer_id: uuid.UUID, payload: NoteCreate) -> Note:
    _require_active(get_customer(db, customer_id))
    note = Note(customer_id=customer_id, body=payload.body)
    db.add(note)
    db.flush()
    db.refresh(note)
    return note


def update_note(db: Session, note_id: uuid.UUID, payload: NoteUpdate) -> Note:
    note = get_note(db, note_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(note, field, value)
    db.flush()
    db.refresh(note)
    return note


def delete_note(
    db: Session, note_id: uuid.UUID, *, storage: Storage | None = None
) -> None:
    note = get_note(db, note_id)
    paths = list(
        db.scalars(select(Attachment.storage_path).where(Attachment.note_id == note_id))
    )
    db.delete(note)
    db.flush()
    if storage is not None:
        _delete_files(storage, paths)


# --------------------------------------------------------------------------- #
# Attachments
# --------------------------------------------------------------------------- #
def list_attachments(db: Session, customer_id: uuid.UUID) -> list[Attachment]:
    get_customer(db, customer_id)
    return list(
        db.scalars(
            select(Attachment)
            .where(Attachment.customer_id == customer_id)
            .order_by(Attachment.created_at.desc(), Attachment.id.desc())
        )
    )


def get_attachment(db: Session, attachment_id: uuid.UUID) -> Attachment:
    attachment = db.get(Attachment, attachment_id)
    if attachment is None:
        raise NotFound(f"attachment {attachment_id} not found")
    return attachment


def create_attachment(
    db: Session,
    customer_id: uuid.UUID,
    *,
    stream: BinaryIO,
    filename: str,
    content_type: str | None,
    note_id: uuid.UUID | None,
    storage: Storage,
) -> Attachment:
    """Stream the upload to storage, then record it.

    If the row insert fails after the bytes land, the orphaned file is removed
    before the error propagates.
    """
    get_customer(db, customer_id)
    if note_id is not None:
        note = get_note(db, note_id)
        if note.customer_id != customer_id:
            raise NotFound(f"note {note_id} not found for customer {customer_id}")

    storage_path, size_bytes = storage.save(stream, filename=filename)
    try:
        attachment = Attachment(
            customer_id=customer_id,
            note_id=note_id,
            filename=filename,
            content_type=content_type or "application/octet-stream",
            size_bytes=size_bytes,
            storage_path=storage_path,
        )
        db.add(attachment)
        db.flush()
        db.refresh(attachment)
        return attachment
    except BaseException:
        storage.delete(storage_path)
        raise


def delete_attachment(
    db: Session, attachment_id: uuid.UUID, *, storage: Storage
) -> None:
    attachment = get_attachment(db, attachment_id)
    storage_path = attachment.storage_path
    db.delete(attachment)
    db.flush()
    storage.delete(storage_path)
