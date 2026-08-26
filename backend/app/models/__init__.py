"""ORM models, re-exported so Alembic autogenerate sees every table."""

from app.db.base import Base
from app.models.channel import (
    Channel,
    ChannelMessage,
)
from app.models.customer import (
    Attachment,
    ContactDetail,
    Customer,
    Interaction,
    Note,
)
from app.models.ticket import (
    Agent,
    Ticket,
    TicketCategory,
    TicketEvent,
)

__all__ = [
    "Base",
    "Agent",
    "Attachment",
    "Channel",
    "ChannelMessage",
    "ContactDetail",
    "Customer",
    "Interaction",
    "Note",
    "Ticket",
    "TicketCategory",
    "TicketEvent",
]
