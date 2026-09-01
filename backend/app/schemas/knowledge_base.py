"""Pydantic v2 schemas for the knowledge-base API.

Ids are ``uuid.UUID`` throughout, matching every other schema module.
``ArticleSummary`` is the trimmed shape returned by list endpoints (agent and
portal alike) -- neither needs the full markdown ``body`` before the reader
opens one article.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.customer import NonEmptyStr

ArticleKind = Literal["faq", "help", "guide"]
ArticleStatus = Literal["draft", "published"]


# --------------------------------------------------------------------------- #
# Categories
# --------------------------------------------------------------------------- #
class ArticleCategoryBase(BaseModel):
    slug: NonEmptyStr = Field(max_length=128)
    name: NonEmptyStr = Field(max_length=200)
    description: str | None = None
    sort_order: int = 0


class ArticleCategoryCreate(ArticleCategoryBase):
    pass


class ArticleCategoryUpdate(BaseModel):
    slug: NonEmptyStr | None = Field(default=None, max_length=128)
    name: NonEmptyStr | None = Field(default=None, max_length=200)
    description: str | None = None
    sort_order: int | None = None


class ArticleCategoryRead(ArticleCategoryBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------- #
# Articles
# --------------------------------------------------------------------------- #
class ArticleBase(BaseModel):
    slug: NonEmptyStr = Field(max_length=200)
    title: NonEmptyStr = Field(max_length=255)
    summary: str | None = Field(default=None, max_length=500)
    body: str = ""
    kind: ArticleKind
    status: ArticleStatus = "draft"
    category_id: uuid.UUID | None = None


class ArticleCreate(ArticleBase):
    pass


class ArticleUpdate(BaseModel):
    slug: NonEmptyStr | None = Field(default=None, max_length=200)
    title: NonEmptyStr | None = Field(default=None, max_length=255)
    summary: str | None = Field(default=None, max_length=500)
    body: str | None = None
    kind: ArticleKind | None = None
    status: ArticleStatus | None = None
    category_id: uuid.UUID | None = None


class ArticleRead(ArticleBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    view_count: int
    author_agent_id: uuid.UUID | None
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime
    category: ArticleCategoryRead | None = None


class ArticleSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    title: str
    summary: str | None
    kind: ArticleKind
    status: ArticleStatus
    category_id: uuid.UUID | None
    updated_at: datetime
