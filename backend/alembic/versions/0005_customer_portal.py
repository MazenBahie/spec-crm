"""customer portal

Adds the customer-portal tables: portal_users, portal_sessions, and
ticket_feedback.

Unlike 0001-0004, this migration introduces no new named Postgres enum type:
``ticket_feedback.rating`` is a plain validated integer (1-5, enforced at the
Pydantic schema layer), not a SQLAlchemy ``Enum`` -- ratings are easier to
widen later (e.g. to a 1-10 scale) as a plain column than as an enum. There is
therefore nothing to drop in ``downgrade()`` beyond the three tables
themselves.

Downgrade drops all three tables -- every portal login, session, and piece of
feedback is lost irrecoverably. ``customers``, ``tickets``, and every other
table are untouched.

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-30 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0005'
down_revision: Union[str, None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('portal_users',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('customer_id', sa.Uuid(), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('display_name', sa.String(length=255), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email')
    )
    op.create_index(op.f('ix_portal_users_customer_id'), 'portal_users', ['customer_id'], unique=False)

    op.create_table('portal_sessions',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('portal_user_id', sa.Uuid(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['portal_user_id'], ['portal_users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )
    op.create_index('ix_portal_sessions_portal_user_created', 'portal_sessions', ['portal_user_id', sa.literal_column('created_at DESC')], unique=False)
    op.create_index(op.f('ix_portal_sessions_portal_user_id'), 'portal_sessions', ['portal_user_id'], unique=False)
    op.create_index(op.f('ix_portal_sessions_token_hash'), 'portal_sessions', ['token_hash'], unique=False)
    op.create_index(op.f('ix_portal_sessions_expires_at'), 'portal_sessions', ['expires_at'], unique=False)

    op.create_table('ticket_feedback',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('ticket_id', sa.Uuid(), nullable=False),
    sa.Column('portal_user_id', sa.Uuid(), nullable=True),
    sa.Column('rating', sa.Integer(), nullable=False),
    sa.Column('comment', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['portal_user_id'], ['portal_users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['ticket_id'], ['tickets.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('ticket_id')
    )
    op.create_index('ix_ticket_feedback_ticket_id', 'ticket_feedback', ['ticket_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_ticket_feedback_ticket_id', table_name='ticket_feedback')
    op.drop_table('ticket_feedback')

    op.drop_index(op.f('ix_portal_sessions_expires_at'), table_name='portal_sessions')
    op.drop_index(op.f('ix_portal_sessions_token_hash'), table_name='portal_sessions')
    op.drop_index(op.f('ix_portal_sessions_portal_user_id'), table_name='portal_sessions')
    op.drop_index('ix_portal_sessions_portal_user_created', table_name='portal_sessions')
    op.drop_table('portal_sessions')

    op.drop_index(op.f('ix_portal_users_customer_id'), table_name='portal_users')
    op.drop_table('portal_users')
