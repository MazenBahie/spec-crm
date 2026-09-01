"""ai ticket summaries

Adds ai_summary (nullable text) and ai_summary_generated_at (nullable
timestamp) to tickets, and a new "ai_summary_generated" value to the
pre-existing ticket_event_type Postgres enum.

The two new columns follow the same nullable-with-no-backfill shape as every
other optional Ticket field (due_at, escalated_at, ...) -- an existing ticket
simply has no summary yet, which the frontend renders as "No summary yet."

Widening ticket_event_type is NOT the same operation as adding a KB `kind` or
`status` value (0006_knowledge_base.py): those are plain strings backed by a
CHECK constraint specifically so they could grow without touching a named
type. ticket_event_type is a real Postgres enum
(``app.models.ticket.ticket_event_type_enum``), so growing it needs
``ALTER TYPE ... ADD VALUE``, which:

- is safe to run inside the same transaction Alembic wraps this migration in
  on Postgres 12+, as long as the new value is not also *used* in the same
  transaction -- this migration only adds it, never inserts a row with it;
- has NO reverse operation. Postgres has never supported dropping a single
  value from an enum type. downgrade() therefore only drops the two columns;
  the added enum label is left in place permanently, including after a
  downgrade.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-01 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0007'
down_revision: Union[str, None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('tickets', sa.Column('ai_summary', sa.Text(), nullable=True))
    op.add_column(
        'tickets',
        sa.Column('ai_summary_generated_at', sa.DateTime(timezone=True), nullable=True),
    )
    # IF NOT EXISTS makes this migration safe to re-run against a database
    # where a prior partial run already added the label.
    op.execute("ALTER TYPE ticket_event_type ADD VALUE IF NOT EXISTS 'ai_summary_generated'")


def downgrade() -> None:
    # See module docstring: the added enum label cannot be removed and is
    # left in place. Only the two columns are reversed.
    op.drop_column('tickets', 'ai_summary_generated_at')
    op.drop_column('tickets', 'ai_summary')
