"""Deterministic canned answers for every `AIProvider` capability.

Mirrors `StubDriver`'s role in `app.services.channels.driver`: this is what
`get_ai_provider()` returns whenever AI is disabled or unconfigured, so every
capability built on `AIProvider` degrades to *something* useful rather than
raising or silently disappearing. Every method here is a pure function of
its arguments -- same input always produces the same output shape -- which
is what makes "AI disabled" a testable branch of every downstream story
rather than an untested one.

Deliberately does NOT import `app.services.ai.provider` (no `AIProvider`
base class to inherit from) -- exactly like `StubDriver` does not import
`ChannelDriver`. Structural conformance is checked via `AIProvider` being
`@runtime_checkable`, not via inheritance; this also avoids a circular
import, since `provider.py` imports this module to re-export
`StubAIProvider`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import ClassVar, TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.channel import ChannelMessage
    from app.models.ticket import Ticket, TicketCategory


class StubAIProvider:
    slug: ClassVar[str] = "stub"

    def summarize_ticket(
        self, ticket: "Ticket", messages: "Sequence[ChannelMessage]"
    ) -> str:
        return (
            f'[AI unavailable] "{ticket.subject}" -- {len(messages)} message(s) '
            "in this ticket's thread. Configure CRM_ANTHROPIC_API_KEY and "
            "CRM_AI_ENABLED=true for a real summary."
        )

    def suggest_category(
        self, ticket: "Ticket", categories: "Sequence[TicketCategory]"
    ) -> str | None:
        # Deterministic, not a "best guess": always the first candidate the
        # caller offered, or None if there is nothing to choose from.
        return str(categories[0].id) if categories else None

    def suggest_reply(
        self, ticket: "Ticket", messages: "Sequence[ChannelMessage]"
    ) -> str:
        return (
            f'Thanks for reaching out about "{ticket.subject}". '
            "We're looking into this and will follow up shortly."
        )

    def suggest_solutions(
        self,
        *,
        ticket_subject: str,
        ticket_description: str,
        candidates: Sequence[Mapping[str, str]],
        limit: int,
    ) -> list[str]:
        # Identity pass-through: the caller's own candidate order, truncated.
        # Callers built against this (e.g. Story 12) are written to produce a
        # correct result regardless of what this does, so this stays the
        # simplest honest behaviour rather than a fake re-rank.
        return [c["id"] for c in candidates[:limit]]

    def chat(
        self,
        message: str,
        history: "Sequence[Mapping[str, str]]",
        *,
        context: str | None = None,
    ) -> str:
        return (
            "AI chat is not configured yet. Your message was: "
            f'"{message[:200]}"'
        )
