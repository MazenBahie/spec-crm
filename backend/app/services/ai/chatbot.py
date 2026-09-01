"""AI-chatbot service layer.

Every function here takes ``portal_user_id`` from the caller's verified
session and treats a ``session_id`` belonging to a different portal user as
:class:`~app.services.errors.NotFound`, not
:class:`~app.services.errors.Forbidden` -- the same documented divergence
``app.services.portal`` uses for cross-customer ticket lookups.

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
# Tuning constants -- module-level, not Settings fields (matching
# activity.MENTION_WINDOW_DAYS): algorithmic knobs read by this module
# itself, not deployment config.
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
# ALL of a portal user's sessions within the rolling window below.
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

_UNAVAILABLE_REPLY = (
    "Sorry, the assistant is unavailable right now. Please try again in a "
    "moment, or create a support ticket if this is urgent."
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
    still exceeded, so the most recent turns are the last to go.
    """
    recent = messages[-MAX_HISTORY_MESSAGES:]
    history = [{"role": m.role, "content": m.content} for m in recent]
    total_chars = sum(len(h["content"]) for h in history)
    while total_chars > MAX_HISTORY_CHARS and len(history) > 1:
        dropped = history.pop(0)
        total_chars -= len(dropped["content"])
    return history


def _build_context(db: Session, portal_user: PortalUser, user_message: str) -> str:
    """Grounding text handed to the provider as the ``context`` argument."""
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
    the provider is caught here and turned into a normal, persisted assistant
    message with a clean "unavailable" reply -- not a 500. The user's typed
    message is never lost: it is flushed to the database before the provider
    is ever called.
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
