"""Customer-management HTTP routes.

Service-layer errors are translated centrally by the handlers registered in
``app.main``; these handlers keep the route bodies free of try/except noise.
"""

from __future__ import annotations

import uuid
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.customer import (
    AttachmentRead,
    ContactDetailCreate,
    ContactDetailRead,
    ContactDetailUpdate,
    CustomerCreate,
    CustomerDetailRead,
    CustomerRead,
    CustomerStatus,
    CustomerUpdate,
    InteractionCreate,
    InteractionRead,
    InteractionUpdate,
    NoteCreate,
    NoteRead,
    NoteUpdate,
    Page,
)
from app.services import customers as svc
from app.services.storage import LocalFileStorage, get_storage

router = APIRouter(tags=["customers"])

DbDep = Annotated[Session, Depends(get_db)]
StorageDep = Annotated[LocalFileStorage, Depends(get_storage)]

_CHUNK = 64 * 1024


def _content_disposition(filename: str) -> str:
    """Build a Content-Disposition value that survives latin-1 headers.

    HTTP headers cannot carry arbitrary unicode, so emit an ASCII-safe
    ``filename`` for old clients plus the RFC 5987 ``filename*`` form that
    modern browsers prefer.
    """
    ascii_name = filename.encode("ascii", "replace").decode("ascii").replace('"', "")
    quoted = quote(filename, safe="")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quoted}"


# --------------------------------------------------------------------------- #
# Customers
# --------------------------------------------------------------------------- #
@router.get("/customers", response_model=Page[CustomerRead])
def list_customers(
    db: DbDep,
    q: Annotated[str | None, Query(description="Match display name or company")] = None,
    status_filter: Annotated[CustomerStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[CustomerRead]:
    items, total = svc.list_customers(
        db, q=q, status=status_filter, limit=limit, offset=offset
    )
    return Page[CustomerRead](
        items=[CustomerRead.model_validate(c) for c in items], total=total
    )


@router.post(
    "/customers", response_model=CustomerRead, status_code=status.HTTP_201_CREATED
)
def create_customer(payload: CustomerCreate, db: DbDep) -> CustomerRead:
    return CustomerRead.model_validate(svc.create_customer(db, payload))


@router.get("/customers/{customer_id}", response_model=CustomerDetailRead)
def get_customer(customer_id: uuid.UUID, db: DbDep) -> CustomerDetailRead:
    customer = svc.get_customer(db, customer_id, with_contacts=True)
    return CustomerDetailRead.model_validate(customer)


@router.patch("/customers/{customer_id}", response_model=CustomerRead)
def update_customer(
    customer_id: uuid.UUID, payload: CustomerUpdate, db: DbDep
) -> CustomerRead:
    return CustomerRead.model_validate(svc.update_customer(db, customer_id, payload))


@router.post("/customers/{customer_id}/archive", response_model=CustomerRead)
def archive_customer(customer_id: uuid.UUID, db: DbDep) -> CustomerRead:
    return CustomerRead.model_validate(svc.archive_customer(db, customer_id))


@router.delete("/customers/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_customer(customer_id: uuid.UUID, db: DbDep, storage: StorageDep) -> Response:
    svc.delete_customer(db, customer_id, storage=storage)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------- #
# Contact details
# --------------------------------------------------------------------------- #
@router.get(
    "/customers/{customer_id}/contacts", response_model=list[ContactDetailRead]
)
def list_contacts(customer_id: uuid.UUID, db: DbDep) -> list[ContactDetailRead]:
    return [
        ContactDetailRead.model_validate(c) for c in svc.list_contacts(db, customer_id)
    ]


@router.post(
    "/customers/{customer_id}/contacts",
    response_model=ContactDetailRead,
    status_code=status.HTTP_201_CREATED,
)
def create_contact(
    customer_id: uuid.UUID, payload: ContactDetailCreate, db: DbDep
) -> ContactDetailRead:
    return ContactDetailRead.model_validate(svc.create_contact(db, customer_id, payload))


@router.get(
    "/customers/{customer_id}/contacts/{contact_id}", response_model=ContactDetailRead
)
def get_contact(
    customer_id: uuid.UUID, contact_id: uuid.UUID, db: DbDep
) -> ContactDetailRead:
    return ContactDetailRead.model_validate(svc.get_contact(db, customer_id, contact_id))


@router.patch(
    "/customers/{customer_id}/contacts/{contact_id}", response_model=ContactDetailRead
)
def update_contact(
    customer_id: uuid.UUID,
    contact_id: uuid.UUID,
    payload: ContactDetailUpdate,
    db: DbDep,
) -> ContactDetailRead:
    return ContactDetailRead.model_validate(
        svc.update_contact(db, customer_id, contact_id, payload)
    )


@router.delete(
    "/customers/{customer_id}/contacts/{contact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_contact(customer_id: uuid.UUID, contact_id: uuid.UUID, db: DbDep) -> Response:
    svc.delete_contact(db, customer_id, contact_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------- #
# Interactions
# --------------------------------------------------------------------------- #
@router.get(
    "/customers/{customer_id}/interactions", response_model=Page[InteractionRead]
)
def list_interactions(
    customer_id: uuid.UUID,
    db: DbDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[InteractionRead]:
    items, total = svc.list_interactions(db, customer_id, limit=limit, offset=offset)
    return Page[InteractionRead](
        items=[InteractionRead.model_validate(i) for i in items], total=total
    )


@router.post(
    "/customers/{customer_id}/interactions",
    response_model=InteractionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_interaction(
    customer_id: uuid.UUID, payload: InteractionCreate, db: DbDep
) -> InteractionRead:
    return InteractionRead.model_validate(
        svc.create_interaction(db, customer_id, payload)
    )


@router.get("/interactions/{interaction_id}", response_model=InteractionRead)
def get_interaction(interaction_id: uuid.UUID, db: DbDep) -> InteractionRead:
    return InteractionRead.model_validate(svc.get_interaction(db, interaction_id))


@router.patch("/interactions/{interaction_id}", response_model=InteractionRead)
def update_interaction(
    interaction_id: uuid.UUID, payload: InteractionUpdate, db: DbDep
) -> InteractionRead:
    return InteractionRead.model_validate(
        svc.update_interaction(db, interaction_id, payload)
    )


@router.delete("/interactions/{interaction_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_interaction(interaction_id: uuid.UUID, db: DbDep) -> Response:
    svc.delete_interaction(db, interaction_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------- #
# Notes
# --------------------------------------------------------------------------- #
@router.get("/customers/{customer_id}/notes", response_model=list[NoteRead])
def list_notes(customer_id: uuid.UUID, db: DbDep) -> list[NoteRead]:
    return [NoteRead.model_validate(n) for n in svc.list_notes(db, customer_id)]


@router.post(
    "/customers/{customer_id}/notes",
    response_model=NoteRead,
    status_code=status.HTTP_201_CREATED,
)
def create_note(customer_id: uuid.UUID, payload: NoteCreate, db: DbDep) -> NoteRead:
    return NoteRead.model_validate(svc.create_note(db, customer_id, payload))


@router.get("/notes/{note_id}", response_model=NoteRead)
def get_note(note_id: uuid.UUID, db: DbDep) -> NoteRead:
    return NoteRead.model_validate(svc.get_note(db, note_id))


@router.patch("/notes/{note_id}", response_model=NoteRead)
def update_note(note_id: uuid.UUID, payload: NoteUpdate, db: DbDep) -> NoteRead:
    return NoteRead.model_validate(svc.update_note(db, note_id, payload))


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(note_id: uuid.UUID, db: DbDep, storage: StorageDep) -> Response:
    svc.delete_note(db, note_id, storage=storage)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------- #
# Attachments
# --------------------------------------------------------------------------- #
@router.get(
    "/customers/{customer_id}/attachments", response_model=list[AttachmentRead]
)
def list_attachments(customer_id: uuid.UUID, db: DbDep) -> list[AttachmentRead]:
    return [
        AttachmentRead.model_validate(a) for a in svc.list_attachments(db, customer_id)
    ]


@router.post(
    "/customers/{customer_id}/attachments",
    response_model=AttachmentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_attachment(
    customer_id: uuid.UUID,
    db: DbDep,
    storage: StorageDep,
    file: Annotated[UploadFile, File()],
    note_id: Annotated[uuid.UUID | None, Form()] = None,
) -> AttachmentRead:
    """Upload one file. Streamed to storage; never fully buffered in memory."""
    attachment = svc.create_attachment(
        db,
        customer_id,
        stream=file.file,
        filename=file.filename or "upload",
        content_type=file.content_type,
        note_id=note_id,
        storage=storage,
    )
    return AttachmentRead.model_validate(attachment)


@router.get("/attachments/{attachment_id}")
def download_attachment(
    attachment_id: uuid.UUID, db: DbDep, storage: StorageDep
) -> StreamingResponse:
    attachment = svc.get_attachment(db, attachment_id)
    handle = storage.open(attachment.storage_path)

    def stream() -> object:
        try:
            while chunk := handle.read(_CHUNK):
                yield chunk
        finally:
            handle.close()

    return StreamingResponse(
        stream(),
        media_type=attachment.content_type,
        headers={
            "Content-Disposition": _content_disposition(attachment.filename),
            "Content-Length": str(attachment.size_bytes),
        },
    )


@router.delete("/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_attachment(
    attachment_id: uuid.UUID, db: DbDep, storage: StorageDep
) -> Response:
    svc.delete_attachment(db, attachment_id, storage=storage)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
