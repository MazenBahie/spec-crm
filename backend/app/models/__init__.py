"""ORM models, re-exported so Alembic autogenerate sees every table."""

from app.db.base import Base
from app.models.customer import (
    Attachment,
    ContactDetail,
    Customer,
    Interaction,
    Note,
)

__all__ = [
    "Base",
    "Attachment",
    "ContactDetail",
    "Customer",
    "Interaction",
    "Note",
]
