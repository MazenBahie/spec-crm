"""Public / portal-facing knowledge-base HTTP routes.

No auth dependency at router level -- unlike ``app.api.deps``,
``app.api.deps_portal`` has no optional-auth variant (only
``get_current_portal_user``, which 401s), so these routes simply omit the
dependency rather than depend on something that does not exist. Every
function on the service side already filters to ``status == "published"``, so
there is nothing here for auth to gate anyway.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.customer import Page
from app.schemas.knowledge_base import (
    ArticleCategoryRead,
    ArticleKind,
    ArticleRead,
    ArticleSummary,
)
from app.services import knowledge_base as svc

router = APIRouter(prefix="/portal/kb", tags=["portal-knowledge-base"])

DbDep = Annotated[Session, Depends(get_db)]


@router.get("/categories", response_model=Page[ArticleCategoryRead])
def list_categories(db: DbDep) -> Page[ArticleCategoryRead]:
    items = svc.list_public_categories(db)
    return Page[ArticleCategoryRead](
        items=[ArticleCategoryRead.model_validate(c) for c in items], total=len(items)
    )


@router.get("/articles", response_model=Page[ArticleSummary])
def list_articles(
    db: DbDep,
    kind: ArticleKind | None = None,
    category_slug: str | None = None,
    q: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[ArticleSummary]:
    items, total = svc.list_public_articles(
        db, kind=kind, category_slug=category_slug, q=q, limit=limit, offset=offset
    )
    return Page[ArticleSummary](
        items=[ArticleSummary.model_validate(a) for a in items], total=total
    )


@router.get("/articles/{slug}", response_model=ArticleRead)
def get_article(slug: str, db: DbDep) -> ArticleRead:
    return ArticleRead.model_validate(svc.get_public_article_by_slug(db, slug))
