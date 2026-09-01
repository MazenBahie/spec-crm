"""The real, Anthropic-SDK-backed `AIProvider` implementation.

One `anthropic.Anthropic` client per instance, constructed once in
`__init__` and reused for every method call on that instance --
`get_ai_provider()` decides how often a new instance (and therefore a new
client) gets built; this class does not cache or share state across
instances itself (see `provider.py`'s statelessness note).

Truncation: `MAX_INPUT_CHARS` (12,000 characters, roughly 3,000 tokens)
bounds how much ticket/thread/candidate text is folded into a single
prompt. This is an application-level guard, not a Claude context-window
limit (`claude-opus-5` has a 1M-token window) -- it exists so a
pathologically long support thread cannot silently balloon latency and
per-call cost. When text exceeds the limit, the *tail* (most recent
content) is kept and the earlier portion dropped, on the theory that the
newest messages are the most relevant to summarizing, replying to, or
chatting about a ticket right now -- the same "most recent state, not
oldest" reasoning Story 09 documents for its own `MAX_SUMMARY_MESSAGES` cap.

Non-English ticket content needs no special handling: Claude is
multilingual and this class does not inspect or transform input language.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import ClassVar

import anthropic

from app.models.channel import ChannelMessage
from app.models.ticket import Ticket, TicketCategory
from app.services.ai.errors import AIProviderError

MAX_INPUT_CHARS = 12_000


def _truncate(text: str, limit: int = MAX_INPUT_CHARS) -> str:
    return text if len(text) <= limit else text[-limit:]


def _format_thread(messages: Sequence[ChannelMessage]) -> str:
    return "\n".join(f"[{m.direction}] {m.body}" for m in messages)


class AnthropicProvider:
    slug: ClassVar[str] = "anthropic"

    def __init__(self, *, api_key: str, model: str) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def summarize_ticket(
        self, ticket: Ticket, messages: Sequence[ChannelMessage]
    ) -> str:
        prompt = (
            f"Ticket subject: {ticket.subject}\n"
            f"Ticket description: {_truncate(ticket.description)}\n\n"
            f"Conversation so far:\n{_truncate(_format_thread(messages))}\n\n"
            "Write a concise 2-4 sentence summary of this support ticket "
            "for an agent picking it up."
        )
        return self._complete(prompt, max_tokens=512)

    def suggest_category(
        self, ticket: Ticket, categories: Sequence[TicketCategory]
    ) -> str | None:
        if not categories:
            return None
        options = "\n".join(f"- {c.id}: {c.name}" for c in categories)
        prompt = (
            f"Ticket subject: {ticket.subject}\n"
            f"Ticket description: {_truncate(ticket.description)}\n\n"
            f"Categories:\n{options}\n\n"
            "Reply with only the id of the single best-matching category "
            "above, or the word NONE if none fit well."
        )
        answer = self._complete(prompt, max_tokens=64).strip()
        return None if answer.upper() == "NONE" else answer

    def suggest_reply(
        self, ticket: Ticket, messages: Sequence[ChannelMessage]
    ) -> str:
        prompt = (
            f"Ticket subject: {ticket.subject}\n\n"
            f"Conversation so far:\n{_truncate(_format_thread(messages))}\n\n"
            "Draft a helpful, professional reply from the support agent to "
            "the customer's most recent message. Reply with only the "
            "message text, no preamble."
        )
        return self._complete(prompt, max_tokens=512)

    def suggest_solutions(
        self,
        *,
        ticket_subject: str,
        ticket_description: str,
        candidates: Sequence[Mapping[str, str]],
        limit: int,
    ) -> list[str]:
        if not candidates:
            return []
        listing = "\n".join(
            f"- {c['id']}: {c['title']} -- {c['summary']}" for c in candidates
        )
        prompt = (
            f"Ticket subject: {ticket_subject}\n"
            f"Ticket description: {_truncate(ticket_description)}\n\n"
            f"Candidate knowledge-base articles:\n{_truncate(listing)}\n\n"
            f"List up to {limit} article ids from the list above, one per "
            "line, most relevant first, that could help resolve this "
            "ticket. Use only ids from the list; write nothing else."
        )
        answer = self._complete(prompt, max_tokens=256)
        return [line.strip() for line in answer.splitlines() if line.strip()][:limit]

    def chat(
        self,
        message: str,
        history: Sequence[Mapping[str, str]],
        *,
        context: str | None = None,
    ) -> str:
        context_block = f"{_truncate(context)}\n\n" if context else ""
        convo = "\n".join(f"{turn['role']}: {turn['content']}" for turn in history)
        prompt = f"{context_block}{_truncate(convo)}\nuser: {_truncate(message)}"
        return self._complete(prompt, max_tokens=1024)

    def _complete(self, prompt: str, *, max_tokens: int) -> str:
        # Broad by intent, mirroring the enqueue_outbound precedent
        # (backend/app/services/channels/service.py:132-144): every failure
        # mode from a bad credential to a network blip to a rate limit ends
        # up as one AIProviderError, which is exactly what every caller in
        # Stories 09-13 is documented to catch.
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:
            raise AIProviderError(f"Anthropic call failed: {exc}") from exc

        if getattr(response, "stop_reason", None) == "refusal":
            raise AIProviderError("Anthropic declined to answer this request")

        text = "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )
        return text.strip()
