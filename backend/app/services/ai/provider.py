"""The contract every AI capability calls through.

Mirrors `app.services.channels.driver.ChannelDriver`: a provider is
stateless and holds no session or request context. It is handed plain
domain objects it already needs (a `Ticket`, its `ChannelMessage` thread)
and answers with a plain value -- a string, or a list of ids drawn from a
candidate set the caller supplies. A provider that cannot answer raises
`AIProviderError` instead of returning `None`/an empty string/a sentinel,
exactly as `ChannelDriver.send` raises instead of returning a failed
`SendResult`.

Stateless and thread-safe by construction: an `AIProvider` implementation
holds no mutable instance state between calls (`AnthropicProvider` holds
only a configured SDK client and a model id, both fixed at construction;
`StubAIProvider` holds nothing). Concurrent requests calling the same or
different `AIProvider` instances therefore need no locking -- this matters
because `get_ai_provider()` (below) constructs a fresh instance on every
call rather than caching one.

Test-override mechanism (read this before writing a caller in Stories
09-13): `get_ai_provider()` is a **plain, zero-argument module-level
function**, not a FastAPI dependency. It is called directly from inside
plain `app/services/ai/*.py` functions in every downstream story (e.g.
`ticket_summary.generate_summary(db, ticket_id)` calls
`get_ai_provider()` in its own body, with no provider argument threaded in
from the route) -- and the service layer in this codebase stays FastAPI-free
by convention (`app/api/deps.py:10-12`). `Depends(get_ai_provider)` plus
`application.dependency_overrides[...]` -- the mechanism `get_db`/
`get_storage` use in `backend/tests/conftest.py:91-92` -- does not fit here,
because nothing at route level would ever receive or forward the injected
value in most callers. (Story 13's chatbot router is the one exception:
because its service function accepts `provider: AIProvider` as an explicit
argument, its route *can* also wrap `get_ai_provider` in `Depends(...)` --
nothing here forbids that, it is simply not the mechanism most callers use.)
Instead:

  - Callers import the *module*, not the bare name:
    `from app.services.ai import provider as ai_provider`, then call
    `ai_provider.get_ai_provider()`. This is required, not stylistic --
    `ai_provider.get_ai_provider()` re-reads the module attribute on every
    call, so a test's `monkeypatch.setattr(ai_provider, "get_ai_provider",
    fake_factory)` takes effect. A `from app.services.ai.provider import
    get_ai_provider` bare-name import binds the function at import time and
    would not observe the monkeypatch.
  - Tests that want a real network-free `StubAIProvider` need no monkeypatch
    at all: `get_ai_provider()` already returns one whenever
    `settings.ai_enabled` is `False` or `settings.anthropic_api_key` is
    unset, which is the default in every test environment (no `.env` value
    for either is set by the test suite).
  - Tests that want to exercise a caller's `AIProviderError`-handling branch
    monkeypatch `get_ai_provider` (via the module reference above) to return
    a fake object satisfying the same methods, or to raise directly.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import ClassVar, Protocol, runtime_checkable

from app.core.config import settings
from app.models.channel import ChannelMessage
from app.models.ticket import Ticket, TicketCategory
from app.services.ai.anthropic_provider import AnthropicProvider
from app.services.ai.errors import AIProviderError
from app.services.ai.stub_provider import StubAIProvider

__all__ = [
    "AIProvider",
    "AIProviderError",
    "AnthropicProvider",
    "StubAIProvider",
    "get_ai_provider",
]


@runtime_checkable
class AIProvider(Protocol):
    slug: ClassVar[str]

    def summarize_ticket(
        self, ticket: Ticket, messages: Sequence[ChannelMessage]
    ) -> str:
        """Return a short prose summary of `ticket` and its `messages` thread.

        `messages` is oldest-first, the same order
        `app.services.channels.service.list_messages_for_ticket` returns.
        Raises `AIProviderError` on failure. Called for a ticket with an
        empty thread too (`messages == []`) -- that is a normal call shape,
        not an error case for the provider to special-case.
        """
        ...

    def suggest_category(
        self, ticket: Ticket, categories: Sequence[TicketCategory]
    ) -> str | None:
        """Return the `str(id)` of the best-matching row in `categories`, or
        `None` if none fit well enough to suggest.

        The caller (not this method) is responsible for validating the
        returned id against the real `categories` it passed in before
        applying it to anything -- never trust a provider's answer as
        already-safe, the same discipline Story 12 documents for
        `suggest_solutions` below. Raises `AIProviderError` on failure.
        """
        ...

    def suggest_reply(
        self, ticket: Ticket, messages: Sequence[ChannelMessage]
    ) -> str:
        """Draft a reply an agent could send back on `ticket`.

        Same `messages` shape as `summarize_ticket`. Raises
        `AIProviderError` on failure.
        """
        ...

    def suggest_solutions(
        self,
        *,
        ticket_subject: str,
        ticket_description: str,
        candidates: Sequence[Mapping[str, str]],
        limit: int,
    ) -> list[str]:
        """Pick and order up to `limit` ids from `candidates`.

        Each candidate mapping carries at least `"id"`, `"title"` and
        `"summary"` (plain strings, not ORM rows -- this method takes a
        pre-fetched candidate set from whatever search already produced it,
        e.g. Story 07's `list_public_articles`, so this module never needs
        to import `app.models.knowledge_base`). The returned list is a
        subset of the input ids in the provider's preferred order; it must
        never introduce an id that was not in `candidates` -- a caller
        validates this regardless (see Story 12's own defensive re-check),
        but a correct implementation does not rely on that safety net.
        Raises `AIProviderError` on failure.
        """
        ...

    def chat(
        self,
        message: str,
        history: Sequence[Mapping[str, str]],
        *,
        context: str | None = None,
    ) -> str:
        """Answer `message` given prior turns in `history`.

        Each `history` entry is `{"role": "user" | "assistant", "content":
        str}`, oldest-first. `context` is an optional, pre-assembled block of
        plain text the caller wants grounding the answer -- e.g. Story 13's
        chatbot passes matched knowledge-base excerpts plus a summary of the
        customer's own open tickets, all folded into one string, because a
        general-purpose portal assistant is not anchored to any single
        `Ticket` row the way a ticket-scoped feature would be. Callers that
        do want to ground a chat in one specific ticket pass its rendered
        fields (subject, description, ...) as part of that same `context`
        string rather than a separate typed parameter -- there is deliberately
        only one shape for "extra grounding text" here, not one per caller.
        `None` for a plain conversation with no extra grounding. Raises
        `AIProviderError` on failure.
        """
        ...


def get_ai_provider() -> AIProvider:
    """Return the `AIProvider` this process should use right now.

    Anthropic-backed only when both `settings.ai_enabled` is `True` and
    `settings.anthropic_api_key` is set to a non-empty value; `StubAIProvider`
    otherwise. This is the single place that decision is made -- no caller
    in Stories 09-13 should re-check `settings.ai_enabled` itself, only call
    this function and use whatever it returns (see this module's docstring
    for why this is a plain function rather than a FastAPI dependency).

    Constructs a fresh provider (and, for `AnthropicProvider`, a fresh SDK
    client) on every call rather than caching one. `AIProvider`
    implementations are documented as stateless above specifically so this
    is safe; the cost is a small, unmeasured amount of per-call construction
    overhead, which a future story may remove with `functools.lru_cache` if
    profiling ever shows it matters. Never raises: a missing or invalid key
    falls back to the stub instead of erroring, both here and at import time
    (constructing `anthropic.Anthropic(api_key=...)` does not itself contact
    the network, so an invalid key is only ever discovered on the first real
    call, inside `AnthropicProvider`'s own `try/except`).
    """
    if settings.ai_enabled and settings.anthropic_api_key:
        return AnthropicProvider(api_key=settings.anthropic_api_key, model=settings.ai_model)
    return StubAIProvider()
