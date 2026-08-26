"""agent dashboard

Adds the agent-dashboard tables: agent_tasks, quick_replies, ticket_notes,
activity_events and its activity_event_mentions join table.

``agents`` is NOT created here — it already exists, added by 0002 alongside
ticket assignment. Every table below hangs off that uuid primary key.

Internal notes get their own ``ticket_notes`` table rather than an
``is_internal`` flag on ``channel_messages``: that table describes a delivery
attempt (channel_id, direction and status are all NOT NULL) and a note has none
of those. Keeping them apart means no existing query needs an exclusion filter,
so a note cannot leak into a customer-facing thread by omission.

Downgrade drops all five tables — every task, canned response, internal note and
feed entry is lost irrecoverably — and drops the two named enum types created
here (agent_task_status, quick_reply_scope) so a later upgrade does not fail
with "type already exists".

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-26 16:10:04.771208

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('agent_tasks',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('agent_id', sa.Uuid(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('status', sa.Enum('open', 'done', name='agent_task_status'), server_default='open', nullable=False),
    sa.Column('remind_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('ticket_id', sa.Uuid(), nullable=True),
    sa.Column('customer_id', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    # CASCADE from the agent: a task is meaningless without its owner. SET NULL
    # on the links, because the task outlives the ticket or customer it was
    # filed against — the agent still has to do the thing.
    sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['ticket_id'], ['tickets.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_agent_tasks_agent_status', 'agent_tasks', ['agent_id', 'status'], unique=False)
    op.create_index(op.f('ix_agent_tasks_agent_id'), 'agent_tasks', ['agent_id'], unique=False)
    op.create_index(op.f('ix_agent_tasks_customer_id'), 'agent_tasks', ['customer_id'], unique=False)
    op.create_index(op.f('ix_agent_tasks_remind_at'), 'agent_tasks', ['remind_at'], unique=False)
    op.create_index(op.f('ix_agent_tasks_ticket_id'), 'agent_tasks', ['ticket_id'], unique=False)

    op.create_table('quick_replies',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('scope', sa.Enum('personal', 'team', name='quick_reply_scope'), nullable=False),
    sa.Column('owner_agent_id', sa.Uuid(), nullable=True),
    sa.Column('shortcut', sa.String(length=40), nullable=True),
    sa.Column('title', sa.String(length=120), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    # The scope invariant in the database itself: a violated row would make one
    # agent's personal reply visible to the whole team.
    sa.CheckConstraint(
        "(scope = 'personal' AND owner_agent_id IS NOT NULL)"
        " OR (scope = 'team' AND owner_agent_id IS NULL)",
        name='ck_quick_replies_scope_owner',
    ),
    sa.ForeignKeyConstraint(['owner_agent_id'], ['agents.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_quick_replies_owner_shortcut', 'quick_replies', ['owner_agent_id', 'shortcut'], unique=False)

    op.create_table('ticket_notes',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('ticket_id', sa.Uuid(), nullable=False),
    sa.Column('author_agent_id', sa.Uuid(), nullable=True),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['author_agent_id'], ['agents.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['ticket_id'], ['tickets.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_ticket_notes_ticket_created', 'ticket_notes', ['ticket_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_ticket_notes_author_agent_id'), 'ticket_notes', ['author_agent_id'], unique=False)
    op.create_index(op.f('ix_ticket_notes_ticket_id'), 'ticket_notes', ['ticket_id'], unique=False)

    op.create_table('activity_events',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('agent_id', sa.Uuid(), nullable=True),
    sa.Column('event_type', sa.String(length=40), nullable=False),
    sa.Column('ticket_id', sa.Uuid(), nullable=True),
    sa.Column('customer_id', sa.Uuid(), nullable=True),
    sa.Column('payload', sa.JSON(none_as_null=True).with_variant(postgresql.JSONB(none_as_null=True), 'postgresql'), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['ticket_id'], ['tickets.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_activity_events_agent_id'), 'activity_events', ['agent_id'], unique=False)
    op.create_index(op.f('ix_activity_events_created_at'), 'activity_events', ['created_at'], unique=False)
    # Descending twin of the plain index above: the feed only ever reads the
    # newest rows first.
    op.create_index('ix_activity_events_created_desc', 'activity_events', [sa.literal_column('created_at DESC')], unique=False)
    op.create_index(op.f('ix_activity_events_customer_id'), 'activity_events', ['customer_id'], unique=False)
    op.create_index(op.f('ix_activity_events_ticket_id'), 'activity_events', ['ticket_id'], unique=False)

    op.create_table('activity_event_mentions',
    sa.Column('event_id', sa.Uuid(), nullable=False),
    sa.Column('agent_id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['event_id'], ['activity_events.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('event_id', 'agent_id')
    )
    op.create_index(op.f('ix_activity_event_mentions_agent_id'), 'activity_event_mentions', ['agent_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_activity_event_mentions_agent_id'), table_name='activity_event_mentions')
    # Mentions first: it holds the FK onto activity_events.
    op.drop_table('activity_event_mentions')
    op.drop_index(op.f('ix_activity_events_ticket_id'), table_name='activity_events')
    op.drop_index(op.f('ix_activity_events_customer_id'), table_name='activity_events')
    op.drop_index('ix_activity_events_created_desc', table_name='activity_events')
    op.drop_index(op.f('ix_activity_events_created_at'), table_name='activity_events')
    op.drop_index(op.f('ix_activity_events_agent_id'), table_name='activity_events')
    op.drop_table('activity_events')
    op.drop_index(op.f('ix_ticket_notes_ticket_id'), table_name='ticket_notes')
    op.drop_index(op.f('ix_ticket_notes_author_agent_id'), table_name='ticket_notes')
    op.drop_index('ix_ticket_notes_ticket_created', table_name='ticket_notes')
    op.drop_table('ticket_notes')
    op.drop_index('ix_quick_replies_owner_shortcut', table_name='quick_replies')
    op.drop_table('quick_replies')
    op.drop_index(op.f('ix_agent_tasks_ticket_id'), table_name='agent_tasks')
    op.drop_index(op.f('ix_agent_tasks_remind_at'), table_name='agent_tasks')
    op.drop_index(op.f('ix_agent_tasks_customer_id'), table_name='agent_tasks')
    op.drop_index(op.f('ix_agent_tasks_agent_id'), table_name='agent_tasks')
    op.drop_index('ix_agent_tasks_agent_status', table_name='agent_tasks')
    op.drop_table('agent_tasks')

    # Postgres keeps named enum types after their tables are dropped; remove
    # them so `upgrade` can run again cleanly. No-op on SQLite.
    bind = op.get_bind()
    for enum_name in ('agent_task_status', 'quick_reply_scope'):
        sa.Enum(name=enum_name).drop(bind, checkfirst=True)
