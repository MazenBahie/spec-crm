"""AI-assisted ticket categorization.

Mirrors the shape of app.services.channels.service.enqueue_outbound: the
provider call is a plain, session-free function behind the AIProvider
Protocol (see app.services.ai.provider, Story 08), and this module's job is
to fetch what the provider needs, validate what it hands back, and write the
outcome onto the row -- never to trust the provider's answer as a foreign key
without checking it first.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session

from app.models.ticket import Ticket, TicketCategory, TicketEvent
from app.services.ai import provider as ai_provider
from app.services.tickets import get_ticket, list_categories

logger = logging.getLogger(__name__)


def _match_category(
    raw: str | None, categories: list[TicketCategory]
) -> TicketCategory | None:
    """Validate the provider's answer against the exact list it was offered.

    The provider is a Protocol boundary around a third-party model, and
    nothing stops it echoing back a category name instead of an id, an id
    that belonged to a category deactivated moments ago, or an outright
    hallucination. Matching against `categories` -- the very list passed
    into suggest_category, not a fresh query -- means a match can only ever
    be one of the options the provider was actually given.
    """
    if not raw:
        return None
    try:
        candidate_id = uuid.UUID(raw)
    except ValueError:
        return None
    for category in categories:
        if category.id == candidate_id:
            return category
    return None


def suggest_category(db: Session, ticket_id: uuid.UUID) -> TicketCategory | None:
    """Compute (and persist) the AI's category suggestion for one ticket.

    Returns the matched TicketCategory, or None when there is nothing to
    suggest -- no active categories exist, the provider declined to answer,
    or its answer didn't match a real category. None is a valid, silent
    outcome here; callers that need to surface a *failure* (as opposed to
    "no suggestion") should let AIProviderError propagate instead of calling
    this inside a broad try/except -- see the two call sites in
    app.services.tickets.create_ticket and app.api.routes.tickets.
    """
    ticket = get_ticket(db, ticket_id)
    categories = list_categories(db, active_only=True)

    if not categories:
        # Short-circuit before the provider call: there is nothing to choose
        # between, so asking would only spend a real API call to learn what
        # we already know.
        match = None
    else:
        raw = ai_provider.get_ai_provider().suggest_category(ticket, categories)
        match = _match_category(raw, categories)

    old_id = ticket.ai_suggested_category_id
    new_id = match.id if match else None
    if new_id != old_id:
        ticket.ai_suggested_category_id = new_id
        db.add(
            TicketEvent(
                ticket_id=ticket.id,
                event_type="ai_category_suggested",
                field="ai_suggested_category_id",
                old_value=str(old_id) if old_id else None,
                new_value=str(new_id) if new_id else None,
            )
        )
    db.flush()
    return match
