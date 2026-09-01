"""knowledge base

Adds the knowledge-base tables: kb_article_categories and kb_articles.

``kind`` and ``status`` on kb_articles are plain strings backed by a CHECK
constraint rather than a named Postgres enum -- both are expected to grow
later, and a CHECK is a plain column-constraint migration to widen, not an
``ALTER TYPE``.

Downgrade drops kb_articles before kb_article_categories (FK order) -- every
article and category is lost irrecoverably. No other table is touched.

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-31 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0006'
down_revision: Union[str, None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('kb_article_categories',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('slug', sa.String(length=128), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('sort_order', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('slug')
    )
    op.create_index(op.f('ix_kb_article_categories_slug'), 'kb_article_categories', ['slug'], unique=False)

    op.create_table('kb_articles',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('category_id', sa.Uuid(), nullable=True),
    sa.Column('slug', sa.String(length=200), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('summary', sa.String(length=500), nullable=True),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('status', sa.String(length=20), server_default='draft', nullable=False),
    sa.Column('view_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('author_agent_id', sa.Uuid(), nullable=True),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("kind IN ('faq', 'help', 'guide')", name='ck_kb_articles_kind'),
    sa.CheckConstraint("status IN ('draft', 'published')", name='ck_kb_articles_status'),
    sa.ForeignKeyConstraint(['author_agent_id'], ['agents.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['category_id'], ['kb_article_categories.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('slug')
    )
    op.create_index(op.f('ix_kb_articles_category_id'), 'kb_articles', ['category_id'], unique=False)
    op.create_index(op.f('ix_kb_articles_kind'), 'kb_articles', ['kind'], unique=False)
    op.create_index(op.f('ix_kb_articles_slug'), 'kb_articles', ['slug'], unique=False)
    op.create_index(op.f('ix_kb_articles_status'), 'kb_articles', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_kb_articles_status'), table_name='kb_articles')
    op.drop_index(op.f('ix_kb_articles_slug'), table_name='kb_articles')
    op.drop_index(op.f('ix_kb_articles_kind'), table_name='kb_articles')
    op.drop_index(op.f('ix_kb_articles_category_id'), table_name='kb_articles')
    op.drop_table('kb_articles')

    op.drop_index(op.f('ix_kb_article_categories_slug'), table_name='kb_article_categories')
    op.drop_table('kb_article_categories')
