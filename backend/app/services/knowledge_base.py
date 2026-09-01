"""Knowledge-base service layer.

Pure functions over a SQLAlchemy ``Session`` -- no FastAPI imports. Callers own
the transaction boundary; these functions ``flush`` but never commit.

Two audiences share this module: staff (drafts + published, via the
``list_articles``/``get_article`` family) and the public portal (published
only, via the ``list_public_articles``/``get_public_article_by_slug`` family).
Keeping the ``status == "published"`` filter inside the public functions
themselves -- rather than trusting every call site to remember it -- is what
keeps a draft from ever leaking to a customer.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import case, func, or_, select, update
from sqlalchemy.orm import Session, selectinload

from app.models.knowledge_base import Article, ArticleCategory
from app.schemas.knowledge_base import (
    ArticleCategoryCreate,
    ArticleCategoryUpdate,
    ArticleCreate,
    ArticleUpdate,
)
from app.services.errors import Conflict, NotFound


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Categories
# --------------------------------------------------------------------------- #
def _assert_category_slug_free(
    db: Session, slug: str, *, exclude: uuid.UUID | None = None
) -> None:
    stmt = select(func.count()).select_from(ArticleCategory).where(
        func.lower(ArticleCategory.slug) == slug.strip().lower()
    )
    if exclude is not None:
        stmt = stmt.where(ArticleCategory.id != exclude)
    if (db.scalar(stmt) or 0) > 0:
        raise Conflict(f"a category with slug {slug!r} already exists")


def list_categories(db: Session) -> list[ArticleCategory]:
    return list(
        db.scalars(
            select(ArticleCategory).order_by(
                ArticleCategory.sort_order.asc(), ArticleCategory.name.asc()
            )
        )
    )


def get_category(db: Session, id_or_slug: str) -> ArticleCategory:
    category = _lookup_category(db, id_or_slug)
    if category is None:
        raise NotFound(f"category {id_or_slug} not found")
    return category


def _lookup_category(db: Session, id_or_slug: str) -> ArticleCategory | None:
    try:
        category_id = uuid.UUID(str(id_or_slug))
    except ValueError:
        return db.scalars(
            select(ArticleCategory).where(ArticleCategory.slug == id_or_slug)
        ).first()
    return db.get(ArticleCategory, category_id)


def create_category(db: Session, payload: ArticleCategoryCreate) -> ArticleCategory:
    _assert_category_slug_free(db, payload.slug)
    category = ArticleCategory(**payload.model_dump())
    db.add(category)
    db.flush()
    db.refresh(category)
    return category


def update_category(
    db: Session, category_id: uuid.UUID, payload: ArticleCategoryUpdate
) -> ArticleCategory:
    category = get_category(db, str(category_id))
    data = payload.model_dump(exclude_unset=True)
    if data.get("slug"):
        _assert_category_slug_free(db, data["slug"], exclude=category.id)
    for field, value in data.items():
        setattr(category, field, value)
    db.flush()
    db.refresh(category)
    return category


def delete_category(db: Session, category_id: uuid.UUID, *, force: bool = False) -> None:
    category = get_category(db, str(category_id))
    in_use = db.scalar(
        select(func.count()).select_from(Article).where(Article.category_id == category.id)
    ) or 0
    if in_use > 0 and not force:
        raise Conflict(f"category is in use by {in_use} article(s)")
    # ON DELETE SET NULL detaches any remaining articles at the DB level, so a
    # forced delete needs nothing further here.
    db.delete(category)
    db.flush()


# --------------------------------------------------------------------------- #
# Articles -- staff
# --------------------------------------------------------------------------- #
def _assert_article_slug_free(
    db: Session, slug: str, *, exclude: uuid.UUID | None = None
) -> None:
    stmt = select(func.count()).select_from(Article).where(
        func.lower(Article.slug) == slug.strip().lower()
    )
    if exclude is not None:
        stmt = stmt.where(Article.id != exclude)
    if (db.scalar(stmt) or 0) > 0:
        raise Conflict(f"an article with slug {slug!r} already exists")


def _search_filter(q: str | None):
    """Case-insensitive match across title, summary and body, or ``None``."""
    if not q or not q.strip():
        return None
    pattern = f"%{q.strip().lower()}%"
    return or_(
        func.lower(Article.title).like(pattern),
        func.lower(func.coalesce(Article.summary, "")).like(pattern),
        func.lower(Article.body).like(pattern),
    )


def _search_rank(q: str | None):
    """Title matches first, then summary, then body -- else 0 (no ordering pull)."""
    if not q or not q.strip():
        return None
    pattern = f"%{q.strip().lower()}%"
    return case(
        (func.lower(Article.title).like(pattern), 0),
        (func.lower(func.coalesce(Article.summary, "")).like(pattern), 1),
        else_=2,
    )


def list_articles(
    db: Session,
    *,
    kind: str | None = None,
    status: str | None = None,
    category_id: uuid.UUID | None = None,
    q: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Article], int]:
    filters = []
    if kind:
        filters.append(Article.kind == kind)
    if status:
        filters.append(Article.status == status)
    if category_id is not None:
        filters.append(Article.category_id == category_id)
    search = _search_filter(q)
    if search is not None:
        filters.append(search)

    total = db.scalar(select(func.count()).select_from(Article).where(*filters)) or 0

    stmt = (
        select(Article)
        .options(selectinload(Article.category))
        .where(*filters)
        .limit(limit)
        .offset(offset)
    )
    rank = _search_rank(q)
    if rank is not None:
        stmt = stmt.order_by(rank.asc(), Article.updated_at.desc())
    else:
        stmt = stmt.order_by(Article.updated_at.desc())

    rows = db.scalars(stmt).all()
    return list(rows), total


def get_article(db: Session, id_or_slug: str) -> Article:
    article = _lookup_article(db, id_or_slug)
    if article is None:
        raise NotFound(f"article {id_or_slug} not found")
    return article


def _lookup_article(db: Session, id_or_slug: str) -> Article | None:
    stmt = select(Article).options(selectinload(Article.category))
    try:
        article_id = uuid.UUID(str(id_or_slug))
    except ValueError:
        return db.scalars(stmt.where(Article.slug == id_or_slug)).first()
    return db.scalars(stmt.where(Article.id == article_id)).first()


def create_article(db: Session, payload: ArticleCreate, *, author_agent_id: uuid.UUID) -> Article:
    _assert_article_slug_free(db, payload.slug)
    if payload.category_id is not None:
        get_category(db, str(payload.category_id))

    data = payload.model_dump()
    published = data.get("status") == "published"
    article = Article(author_agent_id=author_agent_id, **data)
    if published:
        _assert_publishable(article)
        article.published_at = _utcnow()
    db.add(article)
    db.flush()
    db.refresh(article)
    return article


def update_article(db: Session, article_id: uuid.UUID, payload: ArticleUpdate) -> Article:
    article = get_article(db, str(article_id))
    data = payload.model_dump(exclude_unset=True)

    if data.get("slug"):
        _assert_article_slug_free(db, data["slug"], exclude=article.id)
    if "category_id" in data and data["category_id"] is not None:
        get_category(db, str(data["category_id"]))

    was_published = article.status == "published"
    for field, value in data.items():
        setattr(article, field, value)

    if article.status == "published" and not was_published:
        _assert_publishable(article)
        if article.published_at is None:
            article.published_at = _utcnow()

    db.flush()
    db.refresh(article)
    return article


def _assert_publishable(article: Article) -> None:
    if not article.body or not article.body.strip():
        raise Conflict("cannot publish an article with an empty body")


def publish_article(db: Session, article_id: uuid.UUID) -> Article:
    article = get_article(db, str(article_id))
    _assert_publishable(article)
    if article.status != "published":
        article.status = "published"
    if article.published_at is None:
        article.published_at = _utcnow()
    db.flush()
    db.refresh(article)
    return article


def unpublish_article(db: Session, article_id: uuid.UUID) -> Article:
    """Moves an article back to draft. ``published_at`` is left untouched --
    it records when the article was first made public, not its live state."""
    article = get_article(db, str(article_id))
    article.status = "draft"
    db.flush()
    db.refresh(article)
    return article


def delete_article(db: Session, article_id: uuid.UUID) -> None:
    article = get_article(db, str(article_id))
    db.delete(article)
    db.flush()


# --------------------------------------------------------------------------- #
# Articles -- public / portal
# --------------------------------------------------------------------------- #
def list_public_categories(db: Session) -> list[ArticleCategory]:
    """Categories that have at least one published article."""
    return list(
        db.scalars(
            select(ArticleCategory)
            .join(Article, Article.category_id == ArticleCategory.id)
            .where(Article.status == "published")
            .distinct()
            .order_by(ArticleCategory.sort_order.asc(), ArticleCategory.name.asc())
        )
    )


def list_public_articles(
    db: Session,
    *,
    kind: str | None = None,
    category_slug: str | None = None,
    q: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Article], int]:
    filters = [Article.status == "published"]
    if kind:
        filters.append(Article.kind == kind)
    if category_slug:
        filters.append(
            Article.category_id.in_(
                select(ArticleCategory.id).where(ArticleCategory.slug == category_slug)
            )
        )
    search = _search_filter(q)
    if search is not None:
        filters.append(search)

    total = db.scalar(select(func.count()).select_from(Article).where(*filters)) or 0

    stmt = select(Article).where(*filters).limit(limit).offset(offset)
    rank = _search_rank(q)
    if rank is not None:
        stmt = stmt.order_by(rank.asc(), Article.updated_at.desc())
    else:
        stmt = stmt.order_by(Article.updated_at.desc())

    rows = db.scalars(stmt).all()
    return list(rows), total


def get_public_article_by_slug(db: Session, slug: str) -> Article:
    """A published article by slug, with its view count bumped.

    Uses a SQL-level ``UPDATE ... SET view_count = view_count + 1`` rather
    than read-modify-write so two concurrent readers cannot lose an increment.
    """
    article = db.scalars(
        select(Article)
        .options(selectinload(Article.category))
        .where(Article.slug == slug, Article.status == "published")
    ).first()
    if article is None:
        # Never distinguishes "does not exist" from "exists but is a draft" --
        # a portal user cannot learn a draft is being worked on.
        raise NotFound(f"article {slug} not found")

    db.execute(
        update(Article).where(Article.id == article.id).values(view_count=Article.view_count + 1)
    )
    db.flush()
    db.refresh(article)
    return article
