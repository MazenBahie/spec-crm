"""Knowledge-base ORM models.

Two tables: ``kb_article_categories`` group articles for browsing;
``kb_articles`` hold the authored content. ``category_id`` is nullable with
``ON DELETE SET NULL`` so deleting a category never deletes the articles in
it -- they just fall back to uncategorised.

``kind`` and ``status`` are plain validated strings with a CHECK constraint
rather than a named Postgres enum, matching ``ActivityEvent.event_type``
(``app/models/agent.py``): both are expected to grow (a new article kind, a
future ``archived`` status) and a CHECK is one migration to widen, not an
``ALTER TYPE``.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.customer import _pk
from app.models.ticket import Agent

ARTICLE_KINDS = ("faq", "help", "guide")
ARTICLE_STATUSES = ("draft", "published")


class ArticleCategory(Base):
    __tablename__ = "kb_article_categories"

    id: Mapped[uuid.UUID] = _pk()
    slug: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
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

    articles: Mapped[list["Article"]] = relationship(back_populates="category")


class Article(Base):
    __tablename__ = "kb_articles"
    __table_args__ = (
        CheckConstraint("kind IN ('faq', 'help', 'guide')", name="ck_kb_articles_kind"),
        CheckConstraint("status IN ('draft', 'published')", name="ck_kb_articles_status"),
    )

    id: Mapped[uuid.UUID] = _pk()
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("kb_article_categories.id", ondelete="SET NULL"), index=True
    )
    slug: Mapped[str] = mapped_column(String(200), nullable=False, unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str | None] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft", server_default="draft", index=True
    )
    view_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    author_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("agents.id", ondelete="SET NULL")
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    category: Mapped[ArticleCategory | None] = relationship(back_populates="articles")
    author: Mapped[Agent | None] = relationship()
