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
from app.models.knowledge_base import (
    Article,
    ArticleCategory,
)
from app.models.portal import (
    PortalSession,
    PortalUser,
    TicketFeedback,
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
    "Article",
    "ArticleCategory",
    "Attachment",
    "Channel",
    "ChannelMessage",
    "ContactDetail",
    "Customer",
    "Interaction",
    "Note",
    "PortalSession",
    "PortalUser",
    "QuickReply",
    "Ticket",
    "TicketCategory",
    "TicketEvent",
    "TicketFeedback",
    "TicketNote",
]
