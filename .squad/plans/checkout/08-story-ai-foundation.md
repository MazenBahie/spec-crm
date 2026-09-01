# Story 08 — AI Foundation

## Prerequisites

- Story 03 ticket management completed (migration `backend/alembic/versions/0002_ticket_management.py`) — introduces `Agent`, `TicketCategory` and `Ticket` in `backend/app/models/ticket.py`, the domain objects this story's `AIProvider` methods take as arguments.
- Story 04 communication channels completed (migration `0003_communication_channels.py`) — introduces `ChannelMessage` in `backend/app/models/channel.py` (a ticket's message thread) and, more importantly, the `ChannelDriver` Protocol pattern in `backend/app/services/channels/driver.py` that this story's `AIProvider` Protocol is explicitly modeled on.
- No database schema changes in this story — nothing here reads or writes a new table or column, so there is nothing to coordinate with the Alembic chain (`0006_knowledge_base.py` from Story 07 stays `head`). The `## Migration / Rollback` section from earlier stories is intentionally omitted.
- Coordinate with the (parallel) authors of Stories 09–13: every one of them imports from `backend/app/services/ai/provider.py` and depends on the exact method signatures, the test-override mechanism, and the module layout this story defines. Several of those stories were drafted at the same time as this one, before this file existed, and their Context sections say so explicitly (e.g. `.squad/plans/checkout/09-story-ai-ticket-summaries.md` Context §2: *"read this first if it exists on disk by the time you execute this story... every assumption... must be checked against it"*). Two concrete reconciliations a Story 09/10 executor will need to make against what is actually specified below:
  - Story 09's draft assumes `AIProvider.summarize_ticket` takes keyword args `subject=`, `description=`, `messages=[{"direction": ..., "body": ...}, ...]` (plain dicts). This story instead defines `summarize_ticket(ticket: Ticket, messages: Sequence[ChannelMessage]) -> str` (real ORM rows, matching `ChannelDriver.send(message: ChannelMessage)`'s own precedent of taking the row directly rather than a DTO). Story 09's executor must update its call site accordingly.
  - Story 10's draft assumes `AIProviderError` may live in `app.services.ai.provider`; Story 09's draft assumes `app.services.ai.errors`. Both work: this story defines `AIProviderError` canonically in `app.services.ai.errors` and re-exports it from `app.services.ai.provider`, so either import path is valid — see Backend Tasks §5.
  - Story 12's draft already matches this story's real `AIProvider.suggest_solutions` signature and its "import the module, not the bare name, so `monkeypatch.setattr` is visible" test-override guidance exactly — no changes needed there.
  - Story 13's draft assumed `chat(history, user_message, context)` with a `context: str` parameter; this story's first draft instead defined `chat(message, history, *, ticket: Ticket | None = None)`. Reconciled in favor of Story 13's actual need: `chat` now takes `context: str | None`, not `ticket`, because Story 13's chatbot is not anchored to a single ticket (it grounds each turn in a mix of matched KB excerpts and a summary of the customer's open tickets, folded into one pre-assembled string) — a single `Ticket` parameter could not express that. The final signature below is `chat(self, message: str, history: Sequence[Mapping[str, str]], *, context: str | None = None) -> str`; Story 13's executor should call it as `provider.chat(message=content, history=history, context=context)`, not with `user_message=`/`ticket=` keywords.

---

## Story Goal

Backend-only infrastructure story. No ticket-facing feature ships yet, no route is added, and no schema changes — this establishes the reusable AI integration layer that Stories 09–13 (ticket summaries, suggested replies, automatic categorization, suggested solutions, AI chatbot — the five capabilities listed in `.squad/stories/checkout/ai-features/intake.md`) all build on:

1. **Settings** — `anthropic_api_key`, `ai_model`, `ai_enabled` on `Settings` in `backend/app/core/config.py`.
2. **An `AIProvider` Protocol** — `backend/app/services/ai/provider.py` — covering `summarize_ticket`, `suggest_category`, `suggest_reply`, `suggest_solutions` and `chat`, mirroring the shape and raise-don't-return-sentinel discipline of `ChannelDriver` (`backend/app/services/channels/driver.py`).
3. **Two implementations** — `AnthropicProvider` (real `anthropic` SDK client) and `StubAIProvider` (deterministic canned output, mirroring `StubDriver`).
4. **A `get_ai_provider()` factory** — selects between them based on settings, with an explicit, documented test-override mechanism (see Backend Tasks §5 — this is the foundational decision every later story inherits).
5. **`AIProviderError`** — the one exception family every provider implementation raises on failure, distinct from `app.services.errors.ServiceError` and never centrally mapped to an HTTP status, because Story 08 ships no route that could return one.

**Shared contract for the whole arc (not this story's own UI, since it has none): every AI-generated value shown anywhere in the product — a summary, a drafted reply, a suggested category, a suggested article, a chatbot message — must be visually labeled as AI-generated at its point of display.** This applies to `StubAIProvider` output too (see Edge Cases): stub text is still "AI-generated content" from the label's point of view, even though it is not really AI-generated, because the UI has no reliable way to tell a stub answer from a real one and must not try to guess.

**Out of scope:** any ticket-facing feature, any route, any frontend, any Alembic migration, any prompt engineering beyond what makes `AnthropicProvider` functionally correct. Stories 09–13 each own exactly one capability's caller.

---

## Context — Read These Files First

1. `.squad/stories/checkout/ai-features/intake.md` — the arc's intake: five capabilities (ticket summaries, suggested replies, automatic categorization, suggested solutions, AI chatbot), Python + JavaScript hinted as the relevant languages.
2. `backend/app/services/channels/driver.py` (93 lines, read in full) — the `ChannelDriver` Protocol this story's `AIProvider` is modeled on: `SendResult`/`ParsedInbound` frozen dataclasses (lines 21–39), the `@runtime_checkable` `Protocol` with `slug: ClassVar[str]` and methods documented to *raise* on failure rather than return a sentinel (lines 42–61), and `StubDriver` (lines 64–93) — note it does **not** explicitly inherit `ChannelDriver`; it is structurally compatible via `runtime_checkable`, which is why `StubAIProvider`/`AnthropicProvider` below do the same (no import-cycle risk, see Backend Tasks §5/§6).
3. `backend/app/services/channels/registry.py` and `backend/app/services/channels/__init__.py` — a related but **not** directly mirrored pattern: `registry.py` builds a slug→driver dict once at import time because a channel driver is selected by a database-stored slug among five fixed options. `get_ai_provider()` is a simpler binary choice (stub vs. Anthropic) driven by settings, not a registry — do not build a `DRIVERS`-style dict for this story. The `__init__.py` docstring's reasoning for "no re-exports at the package root, to dodge a circular import" is explained there but does not apply the same way to `app.services.ai` — see Backend Tasks §6.
4. `backend/app/core/config.py` (20 lines, read in full) — `Settings(BaseSettings)` at line 4, existing fields `database_url` (line 8), `attachments_dir` (line 12), `portal_session_ttl_days` (line 15), `model_config = SettingsConfigDict(env_file=".env", env_prefix="CRM_", extra="ignore")` at line 17. New fields resolve to `CRM_ANTHROPIC_API_KEY`, `CRM_AI_MODEL`, `CRM_AI_ENABLED`.
5. `backend/app/services/errors.py` (30 lines, read in full) — `ServiceError`/`NotFound`/`Conflict`/`Forbidden`/`PayloadTooLarge`, no `Error` suffix, mapped centrally in `backend/app/main.py`. `AIProviderError` is a **separate** family (see Backend Tasks §5) — it does not subclass `ServiceError` and is not registered in `register_exception_handlers`.
6. `backend/app/main.py` (67 lines, read in full) — `include_router` calls (lines 29–47) and `register_exception_handlers` (lines 52–64), which maps exactly `NotFound`/`Forbidden`/`Conflict`/`PayloadTooLarge` to 404/403/409/413. This story adds no router and no handler here — later stories decide per-route whether an uncaught `AIProviderError` should get its own handler (see Backend Tasks §5's docstring).
7. `backend/app/models/ticket.py` (200 lines, read in full) — `Agent` (lines 64–75), `TicketCategory` (lines 78–92: `id`, `name`, `description`, `default_priority`, `is_active`), and `Ticket` (lines 95–166: `subject: str` required, `description: str` required but may be `""`, `category_id`, `assignee_id`, `status`, `priority`). These are the exact types `AIProvider` methods take as arguments.
8. `backend/app/models/channel.py` (167 lines, read in full) — `ChannelMessage` (lines 101–149: `direction` — `"inbound"`/`"outbound"`, `body: str`, `created_at`). A ticket's message thread, read oldest-first by `app.services.channels.service.list_messages_for_ticket`, is what `summarize_ticket`/`suggest_reply` take as their `messages` argument.
9. `backend/app/services/channels/service.py:96-166` (`enqueue_outbound`) — the codebase's existing best-effort/never-block precedent: a driver's `send()` is called inside a broad `try/except Exception`, and a failure becomes a `status="failed"` row rather than a raised exception up to the route. `AIProviderError` (this story) is what a *caller* in Stories 09–13 will catch to implement the same discipline on their own request paths — Story 08 ships the exception, not a caller, since there is no ticket-mutation path to wire it into yet.
10. `backend/app/api/deps.py:10-12` — the docstring's own stated convention: *"Kept out of `app.services` on purpose: the service layer stays FastAPI-free."* This is the deciding precedent behind Backend Tasks §5's factory-function-not-FastAPI-dependency choice: `get_ai_provider()` is called from deep inside plain `app/services/ai/*.py` functions in every one of Stories 09/10/12's own drafted code, never as a route parameter, so `Depends(get_ai_provider)` would not fit the codebase's own layering rule.
11. `backend/tests/conftest.py` (238 lines, read in full) — the `app` fixture (lines 70–94) uses `application.dependency_overrides[get_db]` / `[get_storage]` for the two things genuinely consumed at route level. This story's tests do **not** add a `get_ai_provider` dependency-override fixture here, for the reason in item 10 — they use `monkeypatch.setattr` directly on the `app.services.ai.provider` module instead (see Test Plan).
12. `backend/pyproject.toml` (currently 27 lines, read in full) — `dependencies` list at lines 6–16. This is the only story in the six-story arc that touches this file.

- Grep for `from app.services.errors import` to confirm no existing code assumes `AIProviderError` belongs to that module.
- Grep for `ClassVar\[str\]` under `backend/app/services/` to confirm `ChannelDriver`/`StubDriver` are the only existing precedent for the `slug` pattern this story reuses.

---

## Backend Tasks

### 1 — Dependency

Edit `backend/pyproject.toml`. Add one line to the `dependencies` list (after `"bcrypt>=4.1",` at line 15):

```toml
    "anthropic>=0.40",
```

This is the only story in the AI-features arc that edits this file; Stories 09–13 depend on it transitively through `backend/app/services/ai/provider.py` and never import `anthropic` themselves.

### 2 — Settings

Edit `backend/app/core/config.py`. Insert after `portal_session_ttl_days` (line 15) and before `model_config` (line 17):

```python
    # AI integration (Story 08). Every AI capability across the arc must
    # degrade to StubAIProvider when ai_enabled is False or no key is
    # configured -- see app/services/ai/provider.py:get_ai_provider(). Never
    # make Anthropic reachability a hard dependency for tests or local dev.
    anthropic_api_key: str | None = None
    ai_model: str = "claude-opus-5"
    ai_enabled: bool = False
```

Resolves from env as `CRM_ANTHROPIC_API_KEY`, `CRM_AI_MODEL`, `CRM_AI_ENABLED` via the existing `env_prefix="CRM_"` on `SettingsConfigDict` (line 17) — no change to `model_config` itself. `ai_model` defaults to a current, real Claude model id (`claude-opus-5`); it is fully overridable per-deployment via `CRM_AI_MODEL` and callers must never hard-code a model id of their own — always read `settings.ai_model` (see `AnthropicProvider.__init__` in §4).

### 3 — Package init

Create file: `backend/app/services/ai/__init__.py`

```python
"""AI integration layer: the `AIProvider` Protocol, its Anthropic-backed and
stub implementations, and the `get_ai_provider()` factory that selects
between them based on `Settings.ai_enabled` / `Settings.anthropic_api_key`.

Deliberately empty of re-exports at the package root. Unlike
`app.services.channels` (whose own `__init__.py` explains a real circular-
import hazard: `service` -> `registry` -> every driver module), there is no
such hazard here -- `stub_provider.py` and `anthropic_provider.py` do not
import `provider.py` -- but the convention in this codebase is still to
import what you need directly:

    from app.services.ai import provider as ai_provider
    from app.services.ai.provider import AIProvider, get_ai_provider
    from app.services.ai.errors import AIProviderError

Importing the *module* rather than a bare name matters for tests that
monkeypatch `get_ai_provider` -- see `provider.py`'s docstring.
"""
```

### 4 — Errors

Create file: `backend/app/services/ai/errors.py`

```python
"""AI-provider infrastructure errors.

Distinct from `app.services.errors.ServiceError` on purpose. Those are
request-validation failures the route layer maps straight to an HTTP status
(`NotFound` -> 404, `Conflict` -> 409, ...) via
`app.main.register_exception_handlers`. `AIProviderError` is an
integration/infrastructure failure -- a timeout, a rate limit, a bad or
revoked credential, a malformed or refused provider response -- and it is
NOT registered in `register_exception_handlers`. It must never reach a route
handler unhandled.

Contract for callers (Stories 09-13, since this story ships no caller of its
own): every `AIProvider` method raises this on failure instead of returning
a sentinel value, mirroring `ChannelDriver.send`'s own documented raise
semantics. No AI call may ever block or fail a synchronous request path that
does not need it -- see `app.services.channels.service.enqueue_outbound`
(`backend/app/services/channels/service.py:132-144`) for this codebase's
existing best-effort precedent: wrap the `AIProvider` call in
`try/except AIProviderError` (or a broader `except Exception`, since a
provider must never leak an un-wrapped SDK exception past this class, but a
defensive caller should not assume that guarantee is airtight) and degrade
to `StubAIProvider` output, a non-AI fallback, or a clean error response --
whichever the specific capability requires. A capability that is itself the
explicit, user-triggered action (e.g. an agent clicking "Regenerate summary")
may instead let `AIProviderError` propagate to a clean 5xx, since failure is
exactly what that caller needs to be told; that is a per-story judgment call,
not a rule enforced here.
"""

from __future__ import annotations


class AIProviderError(Exception):
    """Raised by an `AIProvider` implementation when it cannot produce an answer.

    Covers timeouts, rate limits, invalid/revoked credentials, and malformed
    or refused provider responses alike -- callers should not need to
    distinguish the cause to implement the required best-effort fallback.
    """
```

### 5 — The `AIProvider` Protocol and `get_ai_provider()` factory

Create file: `backend/app/services/ai/provider.py`

```python
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
value. Instead:

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
```

### 6 — `StubAIProvider`

Create file: `backend/app/services/ai/stub_provider.py`

```python
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
```

### 7 — `AnthropicProvider`

Create file: `backend/app/services/ai/anthropic_provider.py`

```python
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
        # Stories 09-13 is documented to catch. Effort "low" plus adaptive
        # thinking: these are short, routine generation/classification
        # calls, not long-horizon reasoning, so a lower effort level keeps
        # latency and cost down without a measurable quality loss.
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                thinking={"type": "adaptive"},
                output_config={"effort": "low"},
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
```

### 8 — Wiring

Nothing to register in `backend/app/main.py` for this story — no router, no new exception handler. `backend/app/services/ai/provider.py` is imported lazily by whichever downstream story needs it; there is no eager import anywhere in `app.main` or `app.models.__init__` to add, since this story introduces no ORM models.

---

## Frontend Tasks

No frontend changes required.

---

## Edge Cases & Failure Modes

- **Missing or invalid API key.** `get_ai_provider()` never raises for this — it falls back to `StubAIProvider` whenever `settings.anthropic_api_key` is falsy, and an *invalid but present* key is only discovered on the first real `messages.create()` call inside `AnthropicProvider._complete`, where it is wrapped into `AIProviderError` like any other SDK failure. Neither case can crash app startup: `Settings()` instantiation and `AnthropicProvider.__init__` (a bare `anthropic.Anthropic(api_key=...)` construction) do not contact the network.
- **Provider timeout / rate limit.** Wrapped into `AIProviderError` by `AnthropicProvider._complete`'s broad `except Exception`. This story ships no caller, so nothing here decides retry policy beyond whatever the `anthropic` SDK does internally by default; the documented contract (`app/services/ai/errors.py`'s module docstring) is that every caller in Stories 09–13 catches `AIProviderError` itself and decides what "AI failed" means for that specific request path.
- **Oversized input.** `MAX_INPUT_CHARS = 12_000` (`anthropic_provider.py`) truncates ticket description, message-thread text, and candidate listings independently, keeping the tail (most recent content) of each. This is an application-level cost/latency guard, not a Claude context-window limit.
- **Non-English ticket content.** No special handling — Claude is multilingual. `AnthropicProvider` does not detect, translate, or reject non-English input.
- **Concurrent requests.** Every `AIProvider` implementation is stateless (see `provider.py`'s module docstring) and `get_ai_provider()` constructs a fresh instance per call rather than sharing a singleton, so there is no shared mutable state for concurrent requests to race on. This also means concurrent callers each pay the (small) cost of constructing a new `anthropic.Anthropic` client — a documented, deliberate tradeoff, not an oversight.
- **`ai_enabled=False` with a configured key, or `ai_enabled=True` with no key.** Both fall back to `StubAIProvider` — `get_ai_provider()` requires *both* conditions to select `AnthropicProvider`. There is no partial/degraded Anthropic mode.
- **Stub output shown to a user.** Per the arc-wide labelling contract in Story Goal, stub output must still be labelled "AI-generated" wherever a downstream story displays it — the UI has no reliable way to distinguish a stub answer from a real one, and must not try to guess based on content.
- **A future caller passes an empty `messages`/`history`/`candidates` sequence.** Every method here is documented to accept this as a normal call shape, not an error: `summarize_ticket`/`suggest_reply` still call through to the model with an empty thread; `suggest_category` returns `None` for empty `categories` without a model call; `suggest_solutions` returns `[]` for empty `candidates` without a model call (skipping a pointless round-trip); `chat` still answers with just `message` and no prior turns.

---

## Test Plan

Backend (add under `backend/tests/`):

1. `backend/tests/test_ai_provider.py`
   - `test_stub_provider_deterministic` — call each `StubAIProvider` method twice with identical in-memory `Ticket`/`ChannelMessage`/`TicketCategory` arguments (constructed directly, not persisted — no `db` fixture needed since nothing is flushed); assert both calls return equal values.
   - `test_stub_provider_output_shapes` — `summarize_ticket`/`suggest_reply`/`chat` return non-empty `str`; `suggest_category` returns `str(categories[0].id)` when given a non-empty list and `None` for an empty list; `suggest_solutions` returns the input candidate ids truncated to `limit`, in order.
   - `test_get_ai_provider_returns_stub_when_disabled` — `monkeypatch.setattr(settings, "ai_enabled", False)`, `monkeypatch.setattr(settings, "anthropic_api_key", "sk-test-would-be-real")`; assert `isinstance(get_ai_provider(), StubAIProvider)`.
   - `test_get_ai_provider_returns_stub_when_no_key` — `monkeypatch.setattr(settings, "ai_enabled", True)`, `monkeypatch.setattr(settings, "anthropic_api_key", None)`; assert `isinstance(get_ai_provider(), StubAIProvider)`.
   - `test_get_ai_provider_returns_anthropic_when_configured` — `monkeypatch.setattr(settings, "ai_enabled", True)`, `monkeypatch.setattr(settings, "anthropic_api_key", "sk-test-fake")`; assert `isinstance(get_ai_provider(), AnthropicProvider)`. No network call happens here — constructing `anthropic.Anthropic(api_key=...)` does not contact Anthropic's servers, so this needs no mocking.
   - `test_anthropic_provider_wraps_sdk_errors` — construct `AnthropicProvider(api_key="fake", model="fake-model")` directly, then `monkeypatch.setattr(provider._client.messages, "create", lambda **_: (_ for _ in ()).throw(RuntimeError("boom")))` (or a small stand-in function) to simulate any SDK failure at the boundary — never a real network call; assert `summarize_ticket(...)` (and at least one other method) raises `AIProviderError`, not the underlying `RuntimeError`.
   - `test_anthropic_provider_truncates_long_input` — build a `Ticket`-like object (or monkeypatch `_truncate` behaviour is exercised indirectly) with a `description` longer than `MAX_INPUT_CHARS`; monkeypatch `messages.create` to capture the `messages` kwarg it was called with; assert the prompt text embedded in it is at most `MAX_INPUT_CHARS` characters for the truncated segment and that it ends with the tail of the original (most-recent-content-kept behaviour).
2. `backend/tests/test_config.py` — **this is the first config test in the suite** (none exists yet; confirmed by `Glob("backend/tests/test_config*.py")` returning no matches at the time this story was written — verify again before writing, in case another story added one first). Follow `backend/tests/conftest.py`'s isolation style (no shared global state — instantiate a fresh `Settings` rather than mutating the module-level `settings` singleton):
   - `test_settings_read_ai_env_vars` — `monkeypatch.setenv("CRM_ANTHROPIC_API_KEY", "sk-test-123")`, `monkeypatch.setenv("CRM_AI_MODEL", "claude-haiku-4-5")`, `monkeypatch.setenv("CRM_AI_ENABLED", "true")`; construct `Settings()` fresh (`from app.core.config import Settings`); assert `.anthropic_api_key == "sk-test-123"`, `.ai_model == "claude-haiku-4-5"`, `.ai_enabled is True`.
   - `test_settings_ai_defaults` — with no `CRM_ANTHROPIC_API_KEY`/`CRM_AI_MODEL`/`CRM_AI_ENABLED` env vars set (use `monkeypatch.delenv(..., raising=False)` for safety), construct `Settings()`; assert `.anthropic_api_key is None`, `.ai_enabled is False`, and `.ai_model` is a non-empty string.

No route exists yet to smoke-test via `TestClient`, and no existing test file needs updating — this story adds no router, no model, and touches no existing endpoint's behaviour.

---

## Verification Steps

1. **Install the new dependency:** `cd backend && uv sync` — picks up `anthropic>=0.40` from the edited `pyproject.toml`.
2. **Backend tests:** `cd backend && uv run pytest -q` — the full existing suite stays green, plus the new `test_ai_provider.py` and `test_config.py` pass. No test in the new files makes a real network call.
3. **Backend still boots with AI unconfigured:** `cd backend && uv run uvicorn app.main:app --reload` with no `CRM_ANTHROPIC_API_KEY`/`CRM_AI_ENABLED` set in the environment (the default). Confirm the process starts with no import-time error or traceback — `app.services.ai.provider` is not imported anywhere in `app.main` yet, so this mainly proves the rest of the app is unaffected; additionally run `python -c "from app.services.ai.provider import get_ai_provider; print(type(get_ai_provider()).__name__)"` from `backend/` and confirm it prints `StubAIProvider` with no exception.
4. **Manual sanity check of the Anthropic path (optional, requires a real key):** with a real `CRM_ANTHROPIC_API_KEY` and `CRM_AI_ENABLED=true` set, run `python -c "from app.services.ai.provider import get_ai_provider; from app.models.ticket import Ticket; p = get_ai_provider(); print(type(p).__name__)"` from `backend/` and confirm it prints `AnthropicProvider`. Not required for CI — this story's automated tests never depend on real credentials.

---

## Done Criteria

- [ ] `backend/pyproject.toml` declares `"anthropic>=0.40"`.
- [ ] `Settings` in `backend/app/core/config.py` exposes `anthropic_api_key: str | None`, `ai_model: str` (defaulting to a real current Claude model id), `ai_enabled: bool` (default `False`), all resolving from `CRM_`-prefixed env vars.
- [ ] `backend/app/services/ai/errors.py` defines `AIProviderError`, documented as a distinct family from `app.services.errors.ServiceError`, never registered in `app.main.register_exception_handlers`.
- [ ] `backend/app/services/ai/provider.py` defines the `AIProvider` Protocol (`summarize_ticket`, `suggest_category`, `suggest_reply`, `suggest_solutions`, `chat`), re-exports `AIProviderError`/`AnthropicProvider`/`StubAIProvider`, and defines `get_ai_provider()`.
- [ ] `backend/app/services/ai/stub_provider.py` defines `StubAIProvider` with deterministic output for every `AIProvider` method.
- [ ] `backend/app/services/ai/anthropic_provider.py` defines `AnthropicProvider`, backed by a real `anthropic.Anthropic` client, truncating oversized input to a documented character limit and wrapping every SDK failure (and a `stop_reason == "refusal"` response) into `AIProviderError`.
- [ ] `get_ai_provider()` returns `StubAIProvider` whenever `ai_enabled` is `False` or `anthropic_api_key` is unset, and `AnthropicProvider` only when both are set — with zero configuration required for the stub path to work (stub fallback works with zero configuration).
- [ ] The test-override mechanism is a plain module-level function callers reach via `from app.services.ai import provider as ai_provider`, monkeypatched directly in tests — not a FastAPI dependency — and this decision is documented in `provider.py`'s own docstring for Stories 09–13 to follow.
- [ ] `backend/tests/test_ai_provider.py` and `backend/tests/test_config.py` pass, and neither makes a real network call.
- [ ] No route, no ORM model, no Alembic migration, and no frontend change ships in this story — this is pure infrastructure for Stories 09–13 to build on.

**STOP HERE. Report to the user and wait for confirmation before proceeding to Story 09.**
