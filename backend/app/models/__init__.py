"""ORM models, re-exported so Alembic autogenerate sees every table."""

from app.db.base import Base
from app.models.agent import (
    ActivityEvent,
    ActivityMention,
    AgentTask,
    QuickReply,
    TicketNote,
)
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
    "ActivityEvent",
    "ActivityMention",
    "Agent",
    "AgentTask",
    "Attachment",
    "Channel",
    "ChannelMessage",
    "ContactDetail",
    "Customer",
    "Interaction",
    "Note",
    "QuickReply",
    "Ticket",
    "TicketCategory",
    "TicketEvent",
    "TicketNote",
]
