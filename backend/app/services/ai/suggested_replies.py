"""Suggested-reply generation. No persistence -- a suggestion is never written
to the database; it exists only for the duration of one request/response.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.services.ai import provider as ai_provider
from app.services.ai.provider import AIProviderError, StubAIProvider
from app.services.channels.service import list_messages_for_ticket
from app.services.tickets import get_ticket

# Matches the limit MessagesPanel itself fetches -- if a thread is longer
# than this, both the agent's own view and the AI's context are truncated
# the same way.
THREAD_CONTEXT_LIMIT = 200


def suggest_reply(db: Session, ticket_id: uuid.UUID) -> str:
    """Draft a reply for ``ticket_id`` from its ticket + message thread.

    Raises ``app.services.errors.NotFound`` (via ``get_ticket``) if the ticket
    does not exist -- the same 404 semantics every other ticket-scoped route
    uses. Does not require an inbound customer message to exist; that gate is
    enforced in the UI, not here, so the API stays simple to call directly
    without silently refusing a reasonable request.
    """
    ticket = get_ticket(db, ticket_id, with_relations=True)
    messages, _total = list_messages_for_ticket(db, ticket_id, limit=THREAD_CONTEXT_LIMIT)

    try:
        return ai_provider.get_ai_provider().suggest_reply(ticket, messages)
    except AIProviderError:
        # Story 08 ships no central handler for AIProviderError and
        # explicitly leaves this decision to each caller -- this is the
        # required fallback for this story, not a placeholder. A suggested
        # reply is optional and always human-reviewed before sending, so
        # degrading to stub output here (rather than surfacing a 502, which
        # Story 09 does for its explicit "Regenerate" action) is the right
        # call for this specific feature.
        return StubAIProvider().suggest_reply(ticket, messages)
