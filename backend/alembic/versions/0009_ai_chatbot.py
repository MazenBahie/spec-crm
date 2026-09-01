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
