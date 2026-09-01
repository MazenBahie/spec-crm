"""Ticket-summary generation.

One function: build the prompt inputs from a ticket's own fields plus its
full message thread, hand them to whatever `AIProvider` Story 08 wired up
(real Anthropic client or `StubAIProvider`), and persist the result on the
Ticket row plus one `ticket_events` row so "when was this last generated" is
visible in the existing History tab with no new UI.

Deliberately synchronous and blocking within the request that calls it: this
is triggered by an explicit "Regenerate" click (see Story Goal -- never on
page load), not by ticket creation or any other path that must stay fast
regardless of AI latency. Contrast with
`app.services.channels.service.enqueue_outbound`, which *is* on such a path
and therefore never lets a provider failure become a raised exception. Here,
letting `AIProviderError` propagate to the route (which turns it into a
clean 5xx) is correct: an agent who clicked "Regenerate" is exactly the
person who needs to be told it failed.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models.ticket import Ticket
from app.services.ai import provider as ai_provider
from app.services.channels.service import list_messages_for_ticket
from app.services.tickets import _now, _record, get_ticket

# Most recent MAX_SUMMARY_MESSAGES are used, not the oldest -- a very long
# thread summarizes its most recent state, not its oldest.
MAX_SUMMARY_MESSAGES = 50


def generate_summary(db: Session, ticket_id: uuid.UUID) -> Ticket:
    """(Re)generate and persist the AI summary for one ticket.

    Loads the ticket (raises `NotFound` via `get_ticket` if it does not
    exist -- the route needs no separate existence check), loads up to the
    most recent `MAX_SUMMARY_MESSAGES` of its thread, and calls the AI
    provider. A ticket with no messages yet still gets a summary -- the
    provider call still happens, with an empty message list, so a brand-new
    ticket's summary is just its subject and description in the agent's
    words rather than an error or a blank state.
    """
    ticket = get_ticket(db, ticket_id, with_relations=True)

    messages, total = list_messages_for_ticket(db, ticket.id, limit=MAX_SUMMARY_MESSAGES, offset=0)
    if total > MAX_SUMMARY_MESSAGES:
        offset = total - MAX_SUMMARY_MESSAGES
        messages, _ = list_messages_for_ticket(
            db, ticket.id, limit=MAX_SUMMARY_MESSAGES, offset=offset
        )

    # Import the module, not the bare name (see the import above): calling
    # `ai_provider.get_ai_provider()` re-reads the module attribute on every
    # call, which is what lets a test's `monkeypatch.setattr(ai_provider,
    # "get_ai_provider", fake_factory)` take effect.
    provider = ai_provider.get_ai_provider()
    summary_text = provider.summarize_ticket(ticket, messages)

    ticket.ai_summary = summary_text
    ticket.ai_summary_generated_at = _now()

    _record(db, ticket, "ai_summary_generated")

    db.flush()
    db.refresh(ticket)
    return ticket
