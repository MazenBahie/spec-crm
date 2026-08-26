"""communication channels

Adds the communication-channel tables: channels (a fixed five-row catalogue,
seeded here) and channel_messages. channel_messages.ticket_id cascades from
tickets.id; channel_id is RESTRICT because the catalogue rows are never meant
to be deleted.

The five seed rows carry hard-coded ids so that a migrated database and a
metadata-created one (the test suite, which seeds via the after_create hook in
app/models/channel.py) hold identical rows. The values are duplicated here
rather than imported from the app: a migration must keep describing the schema
as it was when written, even after the model moves on.

Downgrade drops both tables — every stored inbound and outbound message is
lost irrecoverably — and drops the two named enum types created here
(channel_message_direction, channel_message_status) so a later upgrade does not
fail with "type already exists".

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-26 14:02:11.480215

"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_CHANNEL_SEED = (
    ('c8a1c0de-0000-4000-8000-000000000001', 'email', 'Email'),
    ('c8a1c0de-0000-4000-8000-000000000002', 'whatsapp', 'WhatsApp'),
    ('c8a1c0de-0000-4000-8000-000000000003', 'live_chat', 'Live chat'),
    ('c8a1c0de-0000-4000-8000-000000000004', 'sms', 'SMS'),
    ('c8a1c0de-0000-4000-8000-000000000005', 'web_form', 'Web forms'),
)


def upgrade() -> None:
    channels = op.create_table('channels',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('slug', sa.String(length=32), nullable=False),
    sa.Column('display_name', sa.String(length=64), nullable=False),
    sa.Column('is_enabled', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('config', sa.JSON(none_as_null=True).with_variant(postgresql.JSONB(none_as_null=True), 'postgresql'), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    # Guards the seed below: a re-run after a partial failure fails loudly
    # instead of silently doubling the catalogue.
    sa.UniqueConstraint('slug')
    )
    op.create_table('channel_messages',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('ticket_id', sa.Uuid(), nullable=False),
    sa.Column('channel_id', sa.Uuid(), nullable=False),
    sa.Column('customer_id', sa.Uuid(), nullable=True),
    sa.Column('direction', sa.Enum('inbound', 'outbound', name='channel_message_direction'), nullable=False),
    sa.Column('status', sa.Enum('queued', 'sent', 'delivered', 'failed', 'received', name='channel_message_status'), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('provider_message_id', sa.String(length=255), nullable=True),
    sa.Column('error_reason', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['channel_id'], ['channels.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['ticket_id'], ['tickets.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_channel_messages_created_at'), 'channel_messages', ['created_at'], unique=False)
    op.create_index(op.f('ix_channel_messages_customer_id'), 'channel_messages', ['customer_id'], unique=False)
    op.create_index('ix_channel_messages_ticket_created', 'channel_messages', ['ticket_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_channel_messages_ticket_id'), 'channel_messages', ['ticket_id'], unique=False)

    # Timestamps are supplied rather than left to the column default: the
    # default is `now()`, which SQLite has no such function for, and this is
    # the first migration in the chain that INSERTs at all.
    seeded_at = datetime.now(timezone.utc)
    op.bulk_insert(
        channels,
        [
            {'id': uuid.UUID(channel_id), 'slug': slug, 'display_name': display_name,
             'is_enabled': True, 'config': None,
             'created_at': seeded_at, 'updated_at': seeded_at}
            for channel_id, slug, display_name in _CHANNEL_SEED
        ],
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_channel_messages_ticket_id'), table_name='channel_messages')
    op.drop_index('ix_channel_messages_ticket_created', table_name='channel_messages')
    op.drop_index(op.f('ix_channel_messages_customer_id'), table_name='channel_messages')
    op.drop_index(op.f('ix_channel_messages_created_at'), table_name='channel_messages')
    # channel_messages first: it holds the FK onto channels.
    op.drop_table('channel_messages')
    op.drop_table('channels')

    # Postgres keeps named enum types after their tables are dropped; remove
    # them so `upgrade` can run again cleanly. No-op on SQLite.
    bind = op.get_bind()
    for enum_name in ('channel_message_direction', 'channel_message_status'):
        sa.Enum(name=enum_name).drop(bind, checkfirst=True)
