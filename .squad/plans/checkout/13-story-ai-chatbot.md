# Story 13 — AI Chatbot

## Prerequisites

- **Story 01 (Project init) completed** — FastAPI backend under `backend/app/`, React + Vite frontend under `frontend/src/`, Alembic scaffold.
- **Story 03 (Ticket Management) completed** — `Ticket`, `TicketEvent`, and `backend/app/services/tickets.py` (`get_ticket`, `list_customer_tickets`) exist and are reused, not duplicated.
- **Story 06 (Customer Portal) completed** — this story is built entirely on top of it: `PortalUser`/`PortalSession` (`backend/app/models/portal.py`), `get_current_portal_user`/`CurrentPortalUser` (`backend/app/api/deps_portal.py`), `backend/app/services/portal.py` (`list_portal_tickets`), `backend/app/api/routes/portal.py` as the router-shape template, and `frontend/src/api/portalClient.ts`/`portalAuth.ts` as the only frontend identity path into portal routes.
- **Story 07 (Knowledge Base) completed** — `backend/app/services/knowledge_base.py::list_public_articles` is the published-article search this chatbot grounds its answers with. Confirmed real signature: `list_public_articles(db, *, kind=None, category_slug=None, q=None, limit=20, offset=0) -> tuple[list[Article], int]` (`backend/app/services/knowledge_base.py:298-330`), filtered to `status == "published"` internally.
- **Story 08 (AI Foundation) completed.** This story depends on, and does not redefine:
  - `backend/app/services/ai/provider.py` — an `AIProvider` Protocol (modeled on `backend/app/services/channels/driver.py`'s `ChannelDriver` Protocol, confirmed read in full: `slug: ClassVar[str]`, `send`/`parse_inbound` raise-on-failure style) with a `chat(self, message: str, history: Sequence[Mapping[str, str]], *, context: str | None = None) -> str` method, plus `AnthropicProvider`, `StubAIProvider`, `AIProviderError`, and a `get_ai_provider()` factory. **Confirmed against Story 08's final file**, which landed after this story's first draft: that draft had assumed `chat(history, user_message, context)`, a different parameter order/names. Story 08 reconciled its own signature to exactly the shape above specifically to support this story's need for free-text grounding (see `08-story-ai-foundation.md` Prerequisites) — call it as `provider.chat(message=content, history=history, context=context)`, never with `user_message=` (Backend Task 4 below already uses the corrected call). `get_ai_provider()` is a plain, zero-argument module-level function, not a FastAPI-only construct by design (Story 08's own `provider.py` docstring: the service layer stays FastAPI-free) — nothing stops a route from also wrapping it in `Depends(get_ai_provider)` to inject it as an explicit parameter into a service function, which is the pattern this story's router uses (Backend Task 5), keeping `app.services.ai.chatbot` itself free of any FastAPI import.
  - Settings `anthropic_api_key`, `ai_model`, `ai_enabled` on `Settings` (`backend/app/core/config.py`).
  - The `history` entry shape is confirmed as plain `dict[str, str]` with `role` and `content` keys (Story 08's `Mapping[str, str]` type hint) — this story's `app/services/ai/chatbot.py::_build_history` already builds exactly that shape.
- Stories 09–12 (ticket summaries, suggested replies, automatic categorization, suggested solutions) are siblings, not dependencies — this story shares no table or module with them beyond the common `app/services/ai/provider.py`. Migration `0008_ai_categorization.py` is assumed to exist (`revision='0008'`, `down_revision='0007'`) but was not read; this story's migration only needs its `down_revision` to chain onto it.
- This story's intake is `.squad/stories/checkout/ai-features/intake.md` — item 5 of 5 in the feature description ("AI chatbot").

---

## Story Goal

A logged-in customer-portal user can open a chat page and talk to a KB-grounded AI assistant:

1. The assistant answers using **published** knowledge-base articles (never drafts) and may reference the customer's **own** ticket status — never another customer's data.
2. Conversation history persists per portal user (via a `ChatbotSession`) and is visible again when they return.
3. The assistant never fabricates an answer when nothing relevant exists in the knowledge base — it says so and suggests creating a ticket.
4. The assistant never takes action on the customer's behalf (never creates/edits a ticket itself) — ticket creation stays the existing `POST /portal/tickets` flow (Story 06), requiring the customer's own explicit submission.
5. Every assistant message is visually labeled as AI-generated in the UI, distinct from anything a human agent would send.
6. AI unavailability (disabled, misconfigured, or a live provider error) degrades gracefully to `StubAIProvider` output or a clean in-thread "assistant is unavailable" message — never a 500 that loses the customer's typed message.

**Out of scope:** streaming/token-by-token responses (a single request/response turn per message, matching every other synchronous route in this codebase); multi-session chat (one active `ChatbotSession` per portal user, not per browser tab); staff-side visibility into a customer's chat transcript (a future story, not this one); voice/attachments in chat.

---

## Context — Read These Files First

1. `.squad/stories/checkout/ai-features/intake.md` — this arc's intake; item 5 ("AI chatbot") is this story.
2. `backend/app/models/portal.py` — read in full (123 lines). `PortalUser` (lines 32-58), `PortalSession` (61-91), `TicketFeedback` (94-123) are the exact model-declaration style to mirror: `from __future__ import annotations`, `_pk()` imported from `app.models.customer`, `DateTime(timezone=True)` + `server_default=func.now()` + `onupdate=func.now()` for timestamp pairs, `ForeignKey(..., ondelete=...)`, `Index(...)` in `__table_args__` for a compound index, `TYPE_CHECKING` imports for relationship type hints. `TicketFeedback.rating` (line 110) is a plain validated `Integer`, not an enum — confirms this codebase's preference for CHECK-constrained/validated plain columns over named Postgres enums.
3. `backend/app/services/portal.py` — read in full (214 lines). Module docstring (lines 1-15) states the "cross-customer lookup is `NotFound`, not `Forbidden`" contract verbatim — this story's `list_messages`/`send_message` follow the same rule for a `session_id` belonging to another portal user. `get_portal_ticket` (148-154) is the concrete pattern: look up by id, then compare an owner id, then raise `NotFound` with the *same message shape* as a genuinely missing row.
4. `backend/app/api/deps_portal.py` — read in full (93 lines). `CurrentPortalUser` (line 92) is the dependency alias this story's router uses on every route, exactly as `backend/app/api/routes/portal.py` does — a missing/expired/revoked token or a deactivated portal user are all a single 401 (`_lookup`, lines 37-56); an archived customer is a 403 via `require_active_portal_customer` (75-89).
5. `backend/app/api/routes/portal.py` — read in full (142 lines). This is the router-shape template: `router = APIRouter(prefix="/portal", tags=["portal"])`, `DbDep = Annotated[Session, Depends(get_db)]`, no try/except in route bodies (errors are mapped centrally), one function per row of a route table.
6. `backend/app/services/knowledge_base.py` — read in full (355 lines). `list_public_articles` (298-330) is the grounding source; note it takes `q` as free text and does a case-insensitive `LIKE`/`ILIKE` match across title/summary/body (`_search_filter`, 129-138) — passing the raw customer message as `q` is a reasonable, if blunt, retrieval strategy given no vector search exists in this codebase. `get_public_article_by_slug` (333-354) is **not** used here (the chatbot never opens a single article, only searches).
7. `backend/app/services/errors.py` — all 30 lines. `NotFound`/`Conflict`/`Forbidden`/`PayloadTooLarge`, no `Error` suffix, mapped centrally in `backend/app/main.py`.
8. `backend/app/main.py` — all 67 lines. `include_router(portal.router, ...)` and `include_router(portal_kb.router, ...)` (lines 36-39) are the two nearest precedents — this story's `portal_chat.router` is registered the same way, beside them.
9. `backend/app/services/channels/driver.py` — read in full (94 lines). This is the *shape* Story 08's `AIProvider` Protocol is modeled on (per this arc's shared brief): a `runtime_checkable` `Protocol`, a stub implementation that still behaves usefully rather than crashing the caller outright. Useful context for why `StubAIProvider`'s output is a real (if canned) string, not an exception.
10. `backend/alembic/versions/0006_knowledge_base.py` — read in full (82 lines). Migration-authoring template: bare-number `revision`/`down_revision` strings, `op.create_table` + `sa.CheckConstraint` + `sa.ForeignKeyConstraint` + `op.create_index` ordering in `upgrade()`, FK-aware drop ordering in `downgrade()`. Confirms the CHECK-constrained-string convention (`kb_articles.kind`/`status`, lines 60-61) over a named Postgres enum — this story's `chatbot_messages.role` follows the same convention, so `downgrade()` needs no enum-drop loop.
11. `backend/app/services/activity.py:33` — `MENTION_WINDOW_DAYS = 7`, a module-level tuning constant (not a `Settings` field) for a time-windowed count. This story's rate-limit and context-cap constants follow the same precedent: they are algorithmic tuning knobs read by the service module itself, not deployment config.
12. `backend/app/models/__init__.py` — all 61 lines, alphabetised re-export list; the new `ChatbotSession`/`ChatbotMessage` models are added here.
13. `backend/tests/conftest.py` — read in full (239 lines). `portal_auth`/`portal_user`/`portal_client` fixtures (**lines 183-208**) are reused as-is: `portal_client` is a `TestClient` pre-authenticated with `Authorization: Bearer <token>`, `portal_user` is the signed-up user's dict (`customer_id`, `id`, `email`, `display_name`). `missing_uuid()` (237-238) is reused for 404 tests.
14. `backend/tests/test_portal_tickets.py` — read in full (134 lines). `_second_customer_portal_client` (11-38) is the exact helper this story's cross-user test reuses to build a second, independent portal identity; `test_get_another_customers_ticket_is_404_not_403` (82-102) is the literal pattern for this story's session-ownership 404 test, including asserting the message shape matches the genuinely-missing case.
15. `frontend/src/api/portalClient.ts` — read in full (49 lines). Its header comment (lines 1-8) states explicitly why a portal page must never import `frontend/src/api/client.ts`'s `apiClient`/`agentHeaders()`: the two identity schemes (`X-Agent-Id` vs. portal bearer token) must never be reachable from the same call site. `requestPortal<T>()` already 401-clears the stored session (`clearPortalSession()`, lines 40-45) — the chat client needs no auth handling of its own beyond calling `requestPortal`.
16. `frontend/src/pages/portal/PortalTicketDetailPage.tsx` — read in full (189 lines). The `load()`/`useCallback`/loading-and-error-branch structure (96-134) and the `<dl>`/section rendering style are this story's page-structure template.
17. `frontend/src/PortalApp.tsx` — read in full (87 lines). `PortalShell()` (16-54) is the nav shell (no agent `<Nav>` ever rendered here); the `<Routes>` block (70-84) shows `kb`/`kb/:slug` living outside `PortalProtectedRoute` (no session needed) while `tickets*` lives inside it. The new chat route goes inside `PortalProtectedRoute`, alongside `tickets`.
18. `frontend/src/api/portal.ts` and `frontend/src/api/portalAuth.ts` — read in full. `portal.ts` is the "one function per route-table row" client template; `portalAuth.ts` shows the `portalAuthHeaders()`/`subscribePortalToken` pattern already wired into `portalClient.ts`, needing no new code here.
19. `frontend/src/types/portal.ts` — read in full (52 lines). Mirrors backend Pydantic schemas 1:1 with `string` ids (never `number`); this story's `frontend/src/types/chatbot.ts` follows the identical convention.
20. `frontend/src/pages/portal/__tests__/PortalTicketDetailPage.test.tsx` — read in full (137 lines). The `vi.stubGlobal("fetch", ...)` mock-by-URL-suffix convention (49-82) and the `renderPage()`/`MemoryRouter` wrapper (84-92) are this story's frontend test template.

Grep lines to run before editing:

- `grep -rn "include_router" backend/app/main.py` — confirms current registrations before adding `portal_chat.router`.
- `grep -rn "CurrentPortalUser" backend/app` — confirms every existing call site of the dependency alias this router reuses.
- `grep -n "MENTION_WINDOW_DAYS" backend/app/services/activity.py backend/app/services/agent_dashboard.py` — confirms the module-constant-not-Settings precedent this story's rate-limit/history-cap constants follow.
- `grep -rn "list_public_articles" backend/app` — confirms every existing caller of the KB search function before adding a new one.

---

## Backend Tasks

### 1 — Data model

**Create file:** `backend/app/models/chatbot.py`

A new file, not an addition to `backend/app/models/portal.py`. **Justification:** `knowledge_base.py` (Story 07) set the precedent that a distinct product domain gets its own model file even though it FKs onto `agents`/`kb_article_categories`; the AI-chatbot domain is similarly distinct from core portal auth/session concerns (`PortalUser`/`PortalSession` are about *identity*, `ChatbotSession`/`ChatbotMessage` are about *conversation state*). The counter-precedent (`TicketFeedback` living inside `portal.py` alongside `PortalUser`/`PortalSession`) exists because feedback is a one-row-per-ticket extension of the portal/ticket relationship with no independent lifecycle of its own; a chat thread with growing message history is a large enough concern to warrant its own module. Either placement would work — this choice is stated, not silent.

```python
"""AI-chatbot conversation state.

A ``ChatbotSession`` is a single, long-lived conversation thread per portal
user (get-or-create, not one-per-page-load -- see
``app.services.ai.chatbot.get_or_create_session``). ``ChatbotMessage`` rows are
append-only; nothing here is ever edited in place, unlike ``TicketFeedback``.

Full history is always persisted. Only a capped, recent slice of it is ever
sent to the AI provider on a given turn -- see
``app.services.ai.chatbot.MAX_HISTORY_MESSAGES``/``MAX_HISTORY_CHARS``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.customer import _pk

if TYPE_CHECKING:
    from app.models.portal import PortalUser


class ChatbotSession(Base):
    __tablename__ = "chatbot_sessions"

    id: Mapped[uuid.UUID] = _pk()
    portal_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portal_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    portal_user: Mapped[PortalUser] = relationship(back_populates="chatbot_sessions")
    messages: Mapped[list[ChatbotMessage]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ChatbotMessage.created_at",
    )


class ChatbotMessage(Base):
    __tablename__ = "chatbot_messages"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="ck_chatbot_messages_role"),
        Index("ix_chatbot_messages_session_created", "session_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = _pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chatbot_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Plain CHECK-constrained string, not a named Postgres enum -- matches the
    # kb_articles.kind/status precedent (backend/alembic/versions/0006_knowledge_base.py:60-61),
    # so no enum-drop loop is needed in downgrade().
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Set in Python (default=), not server-side -- SQLite's CURRENT_TIMESTAMP
    # has only second resolution, and two messages in the same turn (user then
    # assistant) would otherwise tie and fall back to random uuid4 ordering,
    # matching the documented reasoning for ticket_events.created_at /
    # channel_messages.created_at (.squad/plans/checkout/00-overview.md,
    # "Shared contracts to respect").
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now(), server_default=func.now()
    )

    session: Mapped[ChatbotSession] = relationship(back_populates="messages")
```

Note `role` is declared `Text` (unbounded) rather than `String(20)` purely so the CHECK constraint is the single source of truth for valid values instead of duplicating the limit in both a length cap and a CHECK; either is fine stylistically, but pick one and do not add both a `String(20)` cap and a values-CHECK that could drift out of sync.

**File:** `backend/app/models/portal.py`

Add to the `PortalUser` relationship block, after `sessions` (line 58):

```python
    chatbot_sessions: Mapped[list[ChatbotSession]] = relationship(
        back_populates="portal_user", cascade="all, delete-orphan", passive_deletes=True
    )
```

Add `from app.models.chatbot import ChatbotSession` under the existing `TYPE_CHECKING` block (lines 27-29), alongside `Customer`/`Ticket`.

**File:** `backend/app/models/__init__.py`

Add `ChatbotMessage`, `ChatbotSession` to both the import block and the alphabetised `__all__` list (between `Base`/`ActivityEvent`-family entries and `Article`, per the existing alphabetical ordering — `ChatbotMessage` and `ChatbotSession` sort between `Attachment` and `Channel`... actually alphabetically `ChatbotMessage` < `ChatbotSession` < `Customer`, and `Channel`/`ChannelMessage` < `ChatbotMessage`. Insert them immediately after `ChannelMessage` and before `ContactDetail`).

---

### 2 — Alembic migration

**Create file:** `backend/alembic/versions/0009_ai_chatbot.py`

```python
"""ai chatbot

Adds chatbot_sessions and chatbot_messages -- one long-lived conversation
thread per portal user, with an append-only message history.

``role`` on chatbot_messages is a plain string backed by a CHECK constraint
(matching the kb_articles.kind/status precedent in 0006_knowledge_base.py),
not a named Postgres enum, so downgrade() needs no enum-drop loop.

Downgrade drops chatbot_messages before chatbot_sessions (FK order) -- every
chat transcript is lost irrecoverably. No other table is touched.

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-01 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0009'
down_revision: Union[str, None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('chatbot_sessions',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('portal_user_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['portal_user_id'], ['portal_users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_chatbot_sessions_portal_user_id'), 'chatbot_sessions', ['portal_user_id'], unique=False)

    op.create_table('chatbot_messages',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('session_id', sa.Uuid(), nullable=False),
    sa.Column('role', sa.Text(), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("role IN ('user', 'assistant')", name='ck_chatbot_messages_role'),
    sa.ForeignKeyConstraint(['session_id'], ['chatbot_sessions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_chatbot_messages_session_id'), 'chatbot_messages', ['session_id'], unique=False)
    op.create_index('ix_chatbot_messages_session_created', 'chatbot_messages', ['session_id', 'created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_chatbot_messages_session_created', table_name='chatbot_messages')
    op.drop_index(op.f('ix_chatbot_messages_session_id'), table_name='chatbot_messages')
    op.drop_table('chatbot_messages')

    op.drop_index(op.f('ix_chatbot_sessions_portal_user_id'), table_name='chatbot_sessions')
    op.drop_table('chatbot_sessions')
```

---

### 3 — Pydantic schemas

**Create file:** `backend/app/schemas/chatbot.py`

Ids are `uuid.UUID` throughout, matching every other schema module in this codebase.

```python
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ChatbotSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    portal_user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class ChatbotMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime


class ChatbotMessageCreate(BaseModel):
    # 4000 chars is a generous chat-turn ceiling with no basis in a real
    # provider limit -- it exists only so one pathological paste can't blow
    # up the context this story builds on every turn. Revisit once Story 08's
    # actual provider token-budgeting is in place.
    content: str = Field(min_length=1, max_length=4000)


class ChatTurnRead(BaseModel):
    """The response to sending one message: both halves of the turn.

    Returning both (not just the assistant reply) means the frontend never
    has to guess the server-assigned id/timestamp of the message it just
    sent -- it renders exactly what was persisted, avoiding any drift between
    an optimistic local echo and the stored row.
    """

    user_message: ChatbotMessageRead
    assistant_message: ChatbotMessageRead
```

---

### 4 — Service layer

**Create file:** `backend/app/services/ai/chatbot.py`

Same contract as `backend/app/services/portal.py`: pure functions over a `Session`, no FastAPI imports, `flush()`/`refresh()` but never `commit()`.

```python
"""AI-chatbot service layer.

Every function here takes ``portal_user_id`` from the caller's verified
session and treats a ``session_id`` belonging to a different portal user as
:class:`~app.services.errors.NotFound`, not :class:`~app.services.errors.Forbidden`
-- the same documented divergence ``app.services.portal`` uses for
cross-customer ticket lookups (.squad/plans/checkout/00-overview.md, "Shared
contracts to respect": "A cross-customer lookup on a portal route returns
404, not 403.").

The assistant only ever informs or suggests. It never creates, updates, or
otherwise acts on a ticket -- ticket creation stays the customer's own
explicit POST /portal/tickets submission (app.services.portal.create_portal_ticket).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.chatbot import ChatbotMessage, ChatbotSession
from app.models.portal import PortalUser
from app.services import knowledge_base as kb_svc
from app.services import portal as portal_svc
from app.services.ai.provider import AIProvider, AIProviderError
from app.services.errors import Conflict, NotFound

# --------------------------------------------------------------------------- #
# Tuning constants -- module-level, not Settings fields, matching the
# activity.MENTION_WINDOW_DAYS precedent (backend/app/services/activity.py:33):
# these are algorithmic knobs read by this module itself, not deployment
# config an operator is expected to override per environment.
# --------------------------------------------------------------------------- #

# History sent to the AI provider each turn is capped two ways -- by count
# and by total characters, whichever is hit first -- while the full,
# untruncated history always stays in chatbot_messages for the customer's own
# later review (GET .../messages never truncates).
MAX_HISTORY_MESSAGES = 20      # most recent messages (~10 user/assistant pairs)
MAX_HISTORY_CHARS = 6000       # combined content length of the capped slice

# Up to this many published KB articles are pulled in as grounding context
# per turn, and up to this many of the customer's own open tickets.
MAX_KB_MATCHES = 3
MAX_OPEN_TICKETS_IN_CONTEXT = 5

# Per-portal-user rate limit: at most this many user-authored messages across
# ALL of a portal user's sessions within the rolling window below. Keyed on
# portal_user_id, not session_id, so a user can't dodge the limit by fetching
# a second session (there is only ever one active session per user in this
# story's design, but the check does not rely on that staying true).
RATE_LIMIT_MAX_MESSAGES = 20
RATE_LIMIT_WINDOW_MINUTES = 10

_NO_KB_MATCH_NOTE = (
    "No matching help-center article was found for this question. Say so "
    "plainly, do not invent an answer, and suggest the customer open a "
    "support ticket if they still need help."
)

_SYSTEM_PREAMBLE = (
    "You are the customer-support assistant embedded in this company's "
    "self-service portal. Answer only using the CONTEXT provided below "
    "(published help-center articles and the customer's own ticket "
    "summaries). Never invent information that is not in the CONTEXT. If "
    "nothing in the CONTEXT answers the question, say you could not find "
    "relevant help and suggest the customer create a support ticket. You "
    "can describe what a ticket submission involves, but you cannot create, "
    "modify, or close a ticket yourself -- only the customer's own action in "
    "this portal can do that."
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def get_or_create_session(db: Session, portal_user_id: uuid.UUID) -> ChatbotSession:
    """One long-lived thread per portal user -- not one per page load."""
    session = db.scalars(
        select(ChatbotSession).where(ChatbotSession.portal_user_id == portal_user_id)
    ).first()
    if session is not None:
        return session
    session = ChatbotSession(portal_user_id=portal_user_id)
    db.add(session)
    db.flush()
    db.refresh(session)
    return session


def _get_owned_session(db: Session, session_id: uuid.UUID, portal_user_id: uuid.UUID) -> ChatbotSession:
    session = db.get(ChatbotSession, session_id)
    if session is None or session.portal_user_id != portal_user_id:
        # Same message shape whether the session belongs to someone else or
        # never existed -- see module docstring.
        raise NotFound(f"chat session {session_id} not found")
    return session


def list_messages(
    db: Session, session_id: uuid.UUID, portal_user_id: uuid.UUID
) -> list[ChatbotMessage]:
    """Full, untruncated history for the customer's own review. Ownership-checked."""
    _get_owned_session(db, session_id, portal_user_id)
    return list(
        db.scalars(
            select(ChatbotMessage)
            .where(ChatbotMessage.session_id == session_id)
            .order_by(ChatbotMessage.created_at)
        )
    )


def _check_rate_limit(db: Session, portal_user_id: uuid.UUID) -> None:
    window_start = _now() - timedelta(minutes=RATE_LIMIT_WINDOW_MINUTES)
    count = db.scalar(
        select(func.count())
        .select_from(ChatbotMessage)
        .join(ChatbotSession, ChatbotSession.id == ChatbotMessage.session_id)
        .where(
            ChatbotSession.portal_user_id == portal_user_id,
            ChatbotMessage.role == "user",
            ChatbotMessage.created_at >= window_start,
        )
    ) or 0
    if count >= RATE_LIMIT_MAX_MESSAGES:
        raise Conflict(
            f"chat message limit reached ({RATE_LIMIT_MAX_MESSAGES} per "
            f"{RATE_LIMIT_WINDOW_MINUTES} minutes) -- please try again shortly"
        )


def _build_history(messages: list[ChatbotMessage]) -> list[dict[str, str]]:
    """Most recent MAX_HISTORY_MESSAGES, then trimmed further to MAX_HISTORY_CHARS.

    Drops the OLDEST of the capped slice first when the character budget is
    still exceeded, so the most recent turns (most relevant to the current
    question) are the last to go.
    """
    recent = messages[-MAX_HISTORY_MESSAGES:]
    history = [{"role": m.role, "content": m.content} for m in recent]
    total_chars = sum(len(h["content"]) for h in history)
    while total_chars > MAX_HISTORY_CHARS and len(history) > 1:
        dropped = history.pop(0)
        total_chars -= len(dropped["content"])
    return history


def _build_context(db: Session, portal_user: PortalUser, user_message: str) -> str:
    """Grounding text handed to the provider as the ``context`` argument.

    Story 08's ``AIProvider.chat(message, history, *, context)`` takes
    ``context`` as a plain string, so the no-fabrication system instruction
    is prepended here rather than passed as a separate parameter the
    Protocol does not define.
    """
    articles, _total = kb_svc.list_public_articles(db, q=user_message, limit=MAX_KB_MATCHES)
    if articles:
        kb_block = "\n\n".join(
            f"Article: {a.title}\nSummary: {a.summary or '(none)'}\n"
            f"Excerpt: {a.body[:500]}"
            for a in articles
        )
    else:
        kb_block = _NO_KB_MATCH_NOTE

    tickets, _total = portal_svc.list_portal_tickets(
        db, portal_user.customer_id, limit=MAX_OPEN_TICKETS_IN_CONTEXT
    )
    open_tickets = [t for t in tickets if not t.is_terminal][:MAX_OPEN_TICKETS_IN_CONTEXT]
    if open_tickets:
        tickets_block = "\n".join(
            f"- {t.reference}: \"{t.subject}\" (status: {t.status})" for t in open_tickets
        )
    else:
        tickets_block = "(the customer has no open tickets right now)"

    return (
        f"{_SYSTEM_PREAMBLE}\n\n"
        f"--- Relevant help-center articles ---\n{kb_block}\n\n"
        f"--- Customer's own open tickets ---\n{tickets_block}"
    )


_UNAVAILABLE_REPLY = (
    "Sorry, the assistant is unavailable right now. Please try again in a "
    "moment, or create a support ticket if this is urgent."
)


def send_message(
    db: Session,
    session_id: uuid.UUID,
    portal_user_id: uuid.UUID,
    content: str,
    *,
    provider: AIProvider,
) -> tuple[ChatbotMessage, ChatbotMessage]:
    """Persists the user's message, gets a reply, persists and returns both.

    Returns ``(user_message, assistant_message)``. An ``AIProviderError`` from
    the provider (disabled, misconfigured, or a live API failure) is caught
    here and turned into a normal, persisted assistant message with a clean
    "unavailable" reply -- not a 500. The user's typed message is never lost:
    it is flushed to the database before the provider is ever called.
    """
    session = _get_owned_session(db, session_id, portal_user_id)
    _check_rate_limit(db, portal_user_id)

    portal_user = db.get(PortalUser, portal_user_id)
    assert portal_user is not None  # guaranteed by CurrentPortalUser at the API layer

    user_message = ChatbotMessage(session_id=session.id, role="user", content=content)
    db.add(user_message)
    db.flush()
    db.refresh(user_message)

    history = _build_history(list(session.messages))  # includes the just-added user message
    context = _build_context(db, portal_user, content)

    try:
        reply_text = provider.chat(message=content, history=history, context=context)
    except AIProviderError:
        reply_text = _UNAVAILABLE_REPLY

    assistant_message = ChatbotMessage(session_id=session.id, role="assistant", content=reply_text)
    db.add(assistant_message)
    session.updated_at = _now()
    db.flush()
    db.refresh(assistant_message)

    return user_message, assistant_message
```

Notes on the design choices above, to make them easy to challenge in review:

- **Rate limit lives in `_check_rate_limit`, called at the top of `send_message`, before the user's message is persisted.** Exceeding it raises `Conflict` (→ HTTP 409, the "429-equivalent" this arc's brief asks for, reusing the existing three-way error mapping rather than inventing a fourth exception type or a raw `HTTPException(429)` in the route). The check counts `role == "user"` rows joined through `ChatbotSession` filtered to the caller's `portal_user_id`, so it is not bypassable by starting a second session (only one session exists per user by construction, but the query does not depend on that).
- **KB grounding calls `list_public_articles(db, q=user_message, ...)` directly** — the raw customer message is the search query. This is a blunt substring match (Story 07's `_search_filter` is `ILIKE`/`LIKE`, not semantic search), so short or oddly-phrased questions may miss an article a human would find. No smarter retrieval exists in this codebase yet; documented here as a known limitation, not fixed by this story.
- **Ticket context is filtered to non-terminal tickets** (`not t.is_terminal`, reusing `Ticket.is_terminal` from `backend/app/models/ticket.py:147-149` the same way Story 06 does) so the assistant does not clutter its context with old, already-resolved tickets that are unlikely to be what the customer is asking about "right now."

---

### 5 — API routes

**Create file:** `backend/app/api/routes/portal_chat.py`

```python
"""Customer-portal AI chatbot routes. Every route requires a valid, active
portal session (CurrentPortalUser) -- there is no anonymous chat."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps_portal import CurrentPortalUser
from app.db.session import get_db
from app.schemas.chatbot import ChatbotMessageCreate, ChatbotMessageRead, ChatbotSessionRead, ChatTurnRead
from app.services.ai import chatbot as svc
from app.services.ai.provider import AIProvider, get_ai_provider

router = APIRouter(prefix="/portal/chat", tags=["portal-chat"])

DbDep = Annotated[Session, Depends(get_db)]
ProviderDep = Annotated[AIProvider, Depends(get_ai_provider)]


@router.post("/sessions", response_model=ChatbotSessionRead)
def start_session(db: DbDep, portal_user: CurrentPortalUser) -> ChatbotSessionRead:
    """Get-or-create: 200 either way, since "created a new one" vs. "found the
    existing one" has no product meaning to the caller (mirrors the same
    reasoning Story 06 used for POST .../feedback's 200-on-both-paths)."""
    session = svc.get_or_create_session(db, portal_user.id)
    return ChatbotSessionRead.model_validate(session)


@router.get("/sessions/{session_id}/messages", response_model=list[ChatbotMessageRead])
def list_messages(
    session_id: uuid.UUID, db: DbDep, portal_user: CurrentPortalUser
) -> list[ChatbotMessageRead]:
    messages = svc.list_messages(db, session_id, portal_user.id)
    return [ChatbotMessageRead.model_validate(m) for m in messages]


@router.post("/sessions/{session_id}/messages", response_model=ChatTurnRead)
def send_message(
    session_id: uuid.UUID,
    payload: ChatbotMessageCreate,
    db: DbDep,
    portal_user: CurrentPortalUser,
    provider: ProviderDep,
) -> ChatTurnRead:
    user_message, assistant_message = svc.send_message(
        db, session_id, portal_user.id, payload.content, provider=provider
    )
    return ChatTurnRead(
        user_message=ChatbotMessageRead.model_validate(user_message),
        assistant_message=ChatbotMessageRead.model_validate(assistant_message),
    )
```

**File:** `backend/app/main.py`

Add `portal_chat` to the router import block (alongside `portal`, `portal_kb`, lines 5-16) and one registration line beside `portal_kb.router` (after line 39):

```python
    # AI chatbot -- requires a valid portal session on every route (unlike
    # portal_kb, which is fully public). Degrades to a clean in-thread
    # message, never a 500, when the AI provider is disabled or fails --
    # see app.services.ai.chatbot.send_message.
    app.include_router(portal_chat.router, prefix=settings.api_prefix)
```

**No other change to `main.py`.** The existing exception handlers already map `NotFound`→404 and `Conflict`→409 — exactly the two this story raises (`Forbidden` is never raised by this story's own code, though a request still 403s if `require_active_portal_customer` rejects it upstream of every route here).

---

## Frontend Tasks

### 6 — Types

**Create file:** `frontend/src/types/chatbot.ts`

Mirrors `backend/app/schemas/chatbot.py` 1:1, `string` ids throughout (matching `frontend/src/types/portal.ts`'s convention, never `number`):

```ts
/** Mirrors the backend Pydantic schemas in app/schemas/chatbot.py. */

export type ChatbotRole = "user" | "assistant";

export interface ChatbotSession {
  id: string;
  portal_user_id: string;
  created_at: string;
  updated_at: string;
}

export interface ChatbotMessage {
  id: string;
  session_id: string;
  role: ChatbotRole;
  content: string;
  created_at: string;
}

export interface ChatbotMessageInput {
  content: string;
}

export interface ChatTurn {
  user_message: ChatbotMessage;
  assistant_message: ChatbotMessage;
}
```

### 7 — Portal API client

**Create file:** `frontend/src/api/portalChat.ts`

Built on `requestPortal` from `frontend/src/api/portalClient.ts` — **never** `frontend/src/api/client.ts`'s `apiClient`, per that file's own header comment on why the two identity schemes must stay unreachable from the same call site.

```ts
/** Typed wrappers for the customer-portal AI chatbot endpoints. */

import { requestPortal } from "./portalClient";
import type { ChatbotMessage, ChatbotMessageInput, ChatbotSession, ChatTurn } from "../types/chatbot";

export function startChatSession(): Promise<ChatbotSession> {
  return requestPortal<ChatbotSession>("/portal/chat/sessions", { method: "POST" });
}

export function listChatMessages(sessionId: string): Promise<ChatbotMessage[]> {
  return requestPortal<ChatbotMessage[]>(`/portal/chat/sessions/${sessionId}/messages`);
}

export function sendChatMessage(sessionId: string, payload: ChatbotMessageInput): Promise<ChatTurn> {
  return requestPortal<ChatTurn>(`/portal/chat/sessions/${sessionId}/messages`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
```

### 8 — Chat page

**Create file:** `frontend/src/pages/portal/PortalChatPage.tsx`

Structured like `PortalTicketDetailPage.tsx`'s `load()`/`useCallback`/loading-and-error-branch split (read in full as this story's template):

- On mount, `load()` calls `startChatSession()` (get-or-create; cheap and idempotent, so calling it on every page visit is fine — it does one `SELECT`, not a new row, once a session already exists) then `listChatMessages(session.id)`, storing both in state.
- Renders the message list: each `ChatbotMessage` as a bubble, right-aligned for `role === "user"`, left-aligned for `role === "assistant"`. **Every assistant bubble carries a visible "AI Assistant" label and a distinct badge/avatar** (e.g. a small robot/sparkle icon via `styles`/`tokens` from `frontend/src/components/ui.tsx` — no new icon library; a text badge is sufficient) so it is never visually confusable with a message from a human agent. This is the concrete implementation of this arc's "AI-generated content must be visually labeled" rule.
- A text `<textarea>`/`<input>` plus a **Send** button and a `<form onSubmit>` (matching the `FeedbackForm` pattern in `PortalTicketDetailPage.tsx`, lines 15-85, for controlled-input + submit-handler style). On submit:
  1. Optimistically append the user's own message to the local list immediately (so the UI feels responsive) using a temporary client-side id.
  2. Call `sendChatMessage(sessionId, { content })`.
  3. On success, **replace** the optimistic user message and append the assistant message with the server-returned `ChatTurn` (using real ids/timestamps — this is exactly why the backend returns both halves of the turn, per `ChatTurnRead`'s docstring in Backend Task 3).
  4. On failure (network error, or a non-2xx the backend did raise — e.g. the 409 rate-limit, or a 401 if the session expired mid-chat), roll back the optimistic message and show the error in an `ErrorBanner`, leaving the customer's typed text recoverable (do not clear the input box on failure) so nothing they typed is lost.
- A `sending` boolean disables the Send button and shows a lightweight "Assistant is thinking…" indicator while awaiting the reply — the round trip includes a live AI call and is not instant.
- Empty-history state: a friendly placeholder line ("Ask a question and the assistant will look through our help center for you.") when `messages.length === 0` after load.

### 9 — Routing and nav

**File:** `frontend/src/PortalApp.tsx`

Add one route inside `PortalProtectedRoute`, alongside `tickets`/`tickets/new`/`tickets/:id` (after line 80):

```tsx
<Route path="chat" element={<PortalChatPage />} />
```

Add the import alongside the other portal page imports (alphabetical, between `PortalArticlePage` and `PortalKnowledgeBasePage`... actually `PortalChatPage` sorts between `PortalArticlePage` and `PortalKnowledgeBasePage` alphabetically — insert accordingly).

**File:** `frontend/src/PortalApp.tsx`, inside `PortalShell()`

Add a nav link to the chat page, visible only when logged in (alongside the existing `user && (...)` block, lines 44-51):

```tsx
{user && (
  <Link to="/portal/chat" style={{ color: tokens.text }}>
    Chat with us
  </Link>
)}
```

(Requires importing `Link` from `react-router-dom` in this file, which it does not currently import — add it to the existing `react-router-dom` import line.)

---

## Edge Cases & Failure Modes

- **Unauthenticated access to any `/portal/chat/*` route** — blocked by `CurrentPortalUser`, the same dependency every other portal data route uses; a missing/expired/revoked token or a deactivated portal user is a 401 (`get_current_portal_user`), an archived customer's still-valid token is a 403 (`require_active_portal_customer`) — no special-casing in this story's router. On the frontend, `requestPortal`'s existing 401 handling (`portalClient.ts:40-45`) calls `clearPortalSession()`, and `PortalProtectedRoute` (`PortalApp.tsx:60-64`) redirects to `/portal/login` on its next render — the chat page needs no bespoke auth-failure handling beyond letting `requestPortal`'s rejection propagate to its `catch` block like any other error.
- **Empty or unpopulated knowledge base** — `_build_context` falls back to `_NO_KB_MATCH_NOTE`, and `_SYSTEM_PREAMBLE` instructs the provider never to fabricate an answer and to suggest a ticket instead. This is a system-prompt-level instruction baked into every call, not a UI-only affordance — even `StubAIProvider` (Story 08) is expected to honor a "no context" signal sensibly, though this story does not control that stub's exact wording.
- **A `session_id` belonging to a different portal user** — `_get_owned_session` raises `NotFound` (→ 404), never `Forbidden`, matching this arc's documented portal contract (`.squad/plans/checkout/00-overview.md`, "Shared contracts to respect"). Covered by `test_cross_user_session_access_is_404` in the Test Plan below, mirroring `test_get_another_customers_ticket_is_404_not_403` (`backend/tests/test_portal_tickets.py:82-102`).
- **Long-running session history growing unbounded** — `list_messages`/`GET .../messages` never truncates (the customer can always scroll their own full history), but `_build_history` caps what is sent to the provider each turn to the most recent `MAX_HISTORY_MESSAGES = 20` messages, further trimmed to `MAX_HISTORY_CHARS = 6000` combined characters by dropping the oldest of that slice first. Both constants live in `backend/app/services/ai/chatbot.py`.
- **Per-user rate limiting to bound API cost** — no rate-limiting mechanism exists anywhere else in this codebase to reuse (Story 06 explicitly flagged the same gap for login attempts). This story adds a narrow, purpose-built one: `_check_rate_limit` in `backend/app/services/ai/chatbot.py`, counting `role == "user"` messages across the caller's `portal_user_id` (joined through their session) created within a rolling `RATE_LIMIT_WINDOW_MINUTES = 10` window; at `RATE_LIMIT_MAX_MESSAGES = 20` it raises `Conflict` (→ HTTP 409) with a message stating the limit and window, before the new message is persisted or the provider is ever called. This is intentionally simple (an in-database rolling count, not a token bucket or external limiter) and does not generalize to other routes — a future story wanting rate limiting elsewhere should not assume this one exists as reusable infrastructure.
- **`AIProviderError` during a chat turn** (AI disabled, misconfigured, or a live provider failure) — caught inside `send_message` itself, *after* the user's message has already been flushed to the database. The response is a normal 200 `ChatTurnRead` whose `assistant_message.content` is a clean, canned "assistant is unavailable" string (`_UNAVAILABLE_REPLY`) — never a 500, and the customer's typed message is never lost (it is already a persisted row by the time the provider is called).
- **The assistant must never act on the customer's behalf** — `send_message` has no code path that calls `portal_svc.create_portal_ticket` or any other mutating ticket function; it only *reads* ticket state for context. The system preamble also explicitly tells the provider it cannot create/modify/close a ticket, in case a customer asks it to "just open a ticket for me."
- **Chat messages may contain customer PII** — `chatbot_messages.content` is free text with no scrubbing/redaction step added by this story. It is subject to the same retention/handling expectations as any other customer-supplied free text already stored in this system (e.g. `Ticket.description`, `Interaction` notes) — no new data-retention policy is introduced or implied here.
- **Malformed UUID in `session_id`** — FastAPI's `uuid.UUID` path coercion returns 422, not 404 or 500, matching every other route in this codebase.
- **A message longer than 4000 characters** — rejected at the schema layer (`ChatbotMessageCreate.content`, `Field(max_length=4000)`) as a 422, before it ever reaches the service or the rate limiter.
- **Concurrent double-submit of the same message** (e.g. a double-click on Send) — not specially guarded server-side; two rapid `POST .../messages` calls simply create two independent turns (two user messages, two assistant replies), which is a reasonable, if slightly wasteful, outcome. The frontend disables the Send button while `sending` is true as the primary mitigation.

---

## Test Plan

Backend — `backend/tests/test_ai_chatbot.py` (new), following the fixture/helper conventions of `backend/tests/test_portal_tickets.py` (read in full) and the `dependency_overrides` pattern already used for `get_db`/`get_storage` in `backend/tests/conftest.py:91-92`.

1. **Session get-or-create idempotency** — `POST /api/portal/chat/sessions` twice with the same `portal_client` returns the same `id` both times; assert via a direct row count of `chatbot_sessions` for that `portal_user_id` (must stay 1).
2. **Send/receive round trip with the stub provider** — override `get_ai_provider` via `app.dependency_overrides[get_ai_provider] = lambda: StubAIProvider()` (Story 08's stub); `POST .../messages` with a body, assert the response is a `ChatTurnRead` whose `user_message.content` echoes the input and whose `assistant_message.role == "assistant"`; assert both rows exist in `chatbot_messages` afterward via `GET .../messages`.
3. **Auth gating** — using the `portal_client`/`portal_user` fixtures (`backend/tests/conftest.py:183-208`): every route under `/api/portal/chat/*` returns 401 for the plain `client` fixture (no `Authorization` header) — mirrors `test_unauthenticated_requests_to_portal_tickets_are_401` (`backend/tests/test_portal_tickets.py:130-133`).
4. **Cross-user session-access returns 404** — build a second, independent portal identity with `_second_customer_portal_client`-style helper (copy the pattern from `backend/tests/test_portal_tickets.py:11-38`); the second user's `GET`/`POST .../messages` against the first user's `session_id` both return 404, and the response `detail` matches the same "chat session ... not found" shape a genuinely-missing `session_id` (`tests.conftest.missing_uuid()`) produces — mirroring `test_get_another_customers_ticket_is_404_not_403`.
5. **Rate-limit behavior once the configured threshold is exceeded** — monkeypatch `app.services.ai.chatbot.RATE_LIMIT_MAX_MESSAGES` down to a small number (e.g. 2) for a fast test; send that many messages successfully, then assert the next `POST .../messages` returns 409 with a `detail` mentioning the limit; assert no new `chatbot_messages` row was created for the rejected attempt (the rate-limit check runs before the user message is persisted).
6. **KB-empty grounding** — with no articles seeded at all, send a message and assert (against the stub provider, which should be configured/asserted to receive the `_NO_KB_MATCH_NOTE` string inside its `context` argument — capture the call via a small recording fake provider rather than the bare `StubAIProvider`, if `StubAIProvider`'s output does not otherwise expose what it was passed) that the context passed to `provider.chat` includes the no-match note. This test's exact assertion depends on `StubAIProvider`'s real interface from Story 08 — if it does not expose call arguments, write a tiny test-local fake implementing `AIProvider` instead, and record `context`/`history`/`user_message` it was called with.
7. **`AIProviderError` degrades to a clean in-thread reply, not a 500** — override `get_ai_provider` with a test-local fake whose `chat()` raises `AIProviderError`; assert the route still returns 200 (a `ChatTurnRead`), `assistant_message.content` equals `_UNAVAILABLE_REPLY`'s text, and the user's original message row still exists (nothing was lost).
8. **Regression** — `backend/tests/test_portal_auth.py`, `test_portal_tickets.py`, `test_portal_feedback.py`, `test_kb_categories_crud.py`, `test_kb_articles_crud.py`, `test_kb_search.py`, `test_kb_portal.py`, and every prior story's suite must all still pass unmodified.

Frontend — `frontend/src/pages/portal/__tests__/PortalChatPage.test.tsx` (new), following the `vi.stubGlobal("fetch", ...)`-by-URL-suffix convention of `PortalTicketDetailPage.test.tsx` (read in full, lines 49-82).

9. **Empty-history initial render** — mock `POST .../sessions` and `GET .../messages` (empty array); assert the empty-state placeholder text renders and no message bubbles are present.
10. **Send-message round trip updates the thread** — mock a `ChatTurn` response from `POST .../messages`; type into the input, click Send, and assert both the user bubble and the AI-labeled assistant bubble appear, the input clears, and the "AI Assistant" label/badge is present on the assistant bubble only (never on the user's own bubble).
11. **Error state when the assistant call fails** — mock `POST .../messages` returning a non-2xx (e.g. 409 for the rate limit, or a network-level rejection); assert an `ErrorBanner`-style message renders, the optimistically-appended user bubble is rolled back (or clearly marked failed — pick one behavior and assert it), and the typed text is not silently lost (still present in the input, or the failed message is easily resendable).

---

## Migration / Rollback

- Migration file `0009_ai_chatbot.py`, `revision = '0009'`, `down_revision = '0008'` (bare numbers, chaining onto Story 12's/sibling `0008_ai_categorization.py`, matching every prior migration's revision-id style).
- Apply with `alembic upgrade head` from `backend/`.
- Rollback with `alembic downgrade -1` — drops `chatbot_messages` before `chatbot_sessions` (FK order). **This destroys every customer's full chat transcript irrecoverably.** No other table is touched; `portal_users`/`portal_sessions`/all ticket/KB data survive untouched.
- No named Postgres enum is introduced (`chatbot_messages.role` is a plain CHECK-constrained string, matching the `kb_articles.kind`/`status` precedent) — so, like `0005_customer_portal.py` and `0006_knowledge_base.py`, there is nothing to drop via a separate enum-drop loop. Stated explicitly in the migration's own docstring so a future reader does not mistake the omission for an oversight against the `0001`-`0004` enum-dropping precedent.
- **Half-applied state:** Alembic runs each migration transactionally on Postgres, so a failed `upgrade` rolls back whole; SQLite (used only by the test suite via `metadata.create_all`, never via this migration file directly) has no equivalent transactional DDL guarantee, but the test suite never runs this migration file — it builds schema from the ORM metadata directly, so this caveat only applies to a real dev/staging Postgres instance run against this file. Matches the caveat already documented in Story 07's own Migration/Rollback section.
- No data backfill required (new tables are empty).

---

## Verification Steps

1. **Backend builds:** `cd backend && uv run alembic upgrade head` — migration applies cleanly on top of the assumed `0008` head.
2. **Backend tests:** `cd backend && uv run pytest -q` — all existing tests still pass, `test_ai_chatbot.py` passes.
3. **Backend serves:** `cd backend && uv run uvicorn app.main:app --reload` — with a portal bearer token (sign up/login via `/api/portal/auth/*` first), `POST /api/portal/chat/sessions`, then `POST /api/portal/chat/sessions/{id}/messages` with a body like `{"content": "How do I reset my password?"}`, and inspect the JSON `ChatTurnRead` response.
4. **Frontend runs:** `cd frontend && npm run dev` — log into the portal, open `/portal/chat`, send a message, confirm the assistant's reply renders with a visible "AI Assistant" label distinct from the user's own bubble, and that a second visit to the page reloads the same conversation history.
5. **Frontend tests:** `cd frontend && npm test` — new and existing suites green.
6. **Regression:** run `pytest -q` and `npm test` again after all changes; open `/portal/tickets`, `/portal/kb`, and the agent dashboard to confirm no navigation or behavior breakage outside the new chat surface.

---

## Done Criteria

- [ ] Alembic migration `0009_ai_chatbot.py` creates `chatbot_sessions` and `chatbot_messages` with the correct FKs, indexes, and a CHECK constraint on `role`; `downgrade()` cleanly reverses in FK order.
- [ ] A logged-in portal user has exactly one `ChatbotSession` (get-or-create, never duplicated) and can send messages to, and receive replies from, the AI assistant via `/api/portal/chat/...`.
- [ ] The assistant grounds its answers in published KB articles (via `list_public_articles`) and the customer's own open tickets, and never leaks another customer's ticket or draft KB content.
- [ ] A `session_id` belonging to a different portal user returns 404, not 403, matching this arc's documented portal contract.
- [ ] When no KB article matches, or the AI provider is disabled/unconfigured/failing, the assistant responds with a clean, honest message (never a fabricated answer, never a 500) and the customer's own typed message is never lost.
- [ ] The assistant never creates, edits, or closes a ticket itself — ticket creation remains the customer's own explicit action via the existing portal ticket flow.
- [ ] History sent to the AI provider each turn is capped (`MAX_HISTORY_MESSAGES` / `MAX_HISTORY_CHARS`), while the customer's full conversation history remains visible via `GET .../messages`.
- [ ] A per-portal-user rate limit bounds message volume and returns a clean 409 (`Conflict`) once exceeded, without ever reaching the AI provider for the rejected request.
- [ ] Every assistant message is visually labeled as AI-generated in the portal chat UI, distinct from any human-agent styling.
- [ ] `backend/app/main.py` registers `portal_chat.router`; `backend/app/models/__init__.py` re-exports `ChatbotSession`/`ChatbotMessage`.
- [ ] All new backend tests (`test_ai_chatbot.py`) and the new frontend test (`PortalChatPage.test.tsx`) pass, and no prior story's test suite regresses.

**STOP HERE. Report to the user — this is the final story in the AI Features arc.**
