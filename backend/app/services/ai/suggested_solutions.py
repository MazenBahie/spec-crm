"""AI-assisted knowledge-base article suggestions for a ticket.

Not a new search engine: the candidate set always comes from Story 07's
real, published-only `list_public_articles` query. The AI provider, when
enabled, only re-ranks/selects among those real rows -- it can never
introduce an article that does not exist, because its output is validated
against the real candidate ids before anything is returned.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models.knowledge_base import Article
from app.services import knowledge_base as kb_svc
from app.services import tickets as tickets_svc
from app.services.ai import provider as ai_provider

MIN_QUERY_LENGTH = 3
CANDIDATE_MULTIPLIER = 4
MIN_CANDIDATE_POOL = 20


def suggest_solutions(
    db: Session, ticket_id: uuid.UUID, *, limit: int = 5
) -> list[Article]:
    """Up to `limit` published articles that might resolve `ticket_id`.

    Raises `NotFound` (via `get_ticket`) if the ticket does not exist. Never
    raises for any other reason -- a missing/failing AI provider, an empty
    knowledge base, or a too-short subject all resolve to a safe list
    (possibly empty), never a 500.
    """
    ticket = tickets_svc.get_ticket(db, ticket_id)

    # A short, title-shaped string like a ticket subject is a far better
    # match key against article *titles* than the long, prose description
    # would be -- concatenating the two would dilute the search pattern into
    # something closer to a paragraph, which matches almost nothing.
    query = ticket.subject.strip()
    if len(query) < MIN_QUERY_LENGTH:
        return []

    pool_size = max(limit * CANDIDATE_MULTIPLIER, MIN_CANDIDATE_POOL)
    candidates, _total = kb_svc.list_public_articles(db, q=query, limit=pool_size, offset=0)
    if not candidates:
        return []

    # Dedupe defensively by id, preserving order -- keeps the contract honest
    # even if a future change adds a second fallback query.
    seen: dict[uuid.UUID, Article] = {}
    for article in candidates:
        seen.setdefault(article.id, article)

    selected_ids: list[str] = []
    try:
        provider = ai_provider.get_ai_provider()
        selected_ids = provider.suggest_solutions(
            ticket_subject=ticket.subject,
            ticket_description=ticket.description,
            candidates=[
                {"id": str(a.id), "title": a.title, "summary": a.summary or ""}
                for a in seen.values()
            ],
            limit=limit,
        )
    except Exception:
        # No AI call may ever block/fail this request path -- fall back to
        # the plain keyword-search order below.
        selected_ids = []

    valid_ids: list[uuid.UUID] = []
    for raw_id in dict.fromkeys(selected_ids):
        try:
            parsed = uuid.UUID(raw_id)
        except (ValueError, TypeError):
            continue
        if parsed in seen:
            valid_ids.append(parsed)

    final_ids = valid_ids[:limit] if valid_ids else list(seen)[:limit]
    return [seen[i] for i in final_ids]
