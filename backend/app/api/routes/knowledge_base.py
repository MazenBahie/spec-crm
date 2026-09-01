"""Staff-facing knowledge-base HTTP routes.

Agent-scoped at router level, matching ``quick_replies.py``: every route below
is 401 without a valid ``X-Agent-Id`` header. Staff see drafts and published
articles alike -- the published-only filter lives entirely in
``portal_kb.py``.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentAgent, get_current_agent
from app.db.session import get_db
from app.schemas.customer import Page
from app.schemas.knowledge_base import (
    ArticleCategoryCreate,
    ArticleCategoryRead,
    ArticleCategoryUpdate,
    ArticleCreate,
    ArticleKind,
    ArticleRead,
    ArticleStatus,
    ArticleSummary,
    ArticleUpdate,
)
from app.services import knowledge_base as svc

router = APIRouter(prefix="/kb", tags=["knowledge-base"], dependencies=[Depends(get_current_agent)])

DbDep = Annotated[Session, Depends(get_db)]


# --------------------------------------------------------------------------- #
# Categories
# --------------------------------------------------------------------------- #
@router.get("/categories", response_model=Page[ArticleCategoryRead])
def list_categories(db: DbDep) -> Page[ArticleCategoryRead]:
    items = svc.list_categories(db)
    return Page[ArticleCategoryRead](
        items=[ArticleCategoryRead.model_validate(c) for c in items], total=len(items)
    )


@router.post(
    "/categories", response_model=ArticleCategoryRead, status_code=status.HTTP_201_CREATED
)
def create_category(payload: ArticleCategoryCreate, db: DbDep) -> ArticleCategoryRead:
    return ArticleCategoryRead.model_validate(svc.create_category(db, payload))


@router.get("/categories/{category_id}", response_model=ArticleCategoryRead)
def get_category(category_id: uuid.UUID, db: DbDep) -> ArticleCategoryRead:
    return ArticleCategoryRead.model_validate(svc.get_category(db, str(category_id)))


@router.patch("/categories/{category_id}", response_model=ArticleCategoryRead)
def update_category(
    category_id: uuid.UUID, payload: ArticleCategoryUpdate, db: DbDep
) -> ArticleCategoryRead:
    return ArticleCategoryRead.model_validate(svc.update_category(db, category_id, payload))


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(
    category_id: uuid.UUID, db: DbDep, force: bool = False
) -> Response:
    svc.delete_category(db, category_id, force=force)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------- #
# Articles
# --------------------------------------------------------------------------- #
@router.get("/articles", response_model=Page[ArticleSummary])
def list_articles(
    db: DbDep,
    agent: CurrentAgent,
    kind: ArticleKind | None = None,
    status: ArticleStatus | None = None,
    category_id: uuid.UUID | None = None,
    q: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[ArticleSummary]:
    items, total = svc.list_articles(
        db, kind=kind, status=status, category_id=category_id, q=q, limit=limit, offset=offset
    )
    return Page[ArticleSummary](
        items=[ArticleSummary.model_validate(a) for a in items], total=total
    )


@router.post("/articles", response_model=ArticleRead, status_code=status.HTTP_201_CREATED)
def create_article(payload: ArticleCreate, db: DbDep, agent: CurrentAgent) -> ArticleRead:
    return ArticleRead.model_validate(
        svc.create_article(db, payload, author_agent_id=agent.id)
    )


@router.get("/articles/{article_id}", response_model=ArticleRead)
def get_article(article_id: uuid.UUID, db: DbDep) -> ArticleRead:
    return ArticleRead.model_validate(svc.get_article(db, str(article_id)))


@router.patch("/articles/{article_id}", response_model=ArticleRead)
def update_article(article_id: uuid.UUID, payload: ArticleUpdate, db: DbDep) -> ArticleRead:
    return ArticleRead.model_validate(svc.update_article(db, article_id, payload))


@router.post("/articles/{article_id}/publish", response_model=ArticleRead)
def publish_article(article_id: uuid.UUID, db: DbDep) -> ArticleRead:
    return ArticleRead.model_validate(svc.publish_article(db, article_id))


@router.post("/articles/{article_id}/unpublish", response_model=ArticleRead)
def unpublish_article(article_id: uuid.UUID, db: DbDep) -> ArticleRead:
    return ArticleRead.model_validate(svc.unpublish_article(db, article_id))


@router.delete("/articles/{article_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_article(article_id: uuid.UUID, db: DbDep) -> Response:
    svc.delete_article(db, article_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
