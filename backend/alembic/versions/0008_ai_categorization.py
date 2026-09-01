"""ai categorization

Adds tickets.ai_suggested_category_id (nullable FK to ticket_categories, ON
DELETE SET NULL, indexed) and a new "ai_category_suggested" value to the
ticket_event_type Postgres enum.

This is the first migration in the codebase to alter an existing table
rather than create a new one, so there is no add_column/create_foreign_key
precedent to copy verbatim; the style below extrapolates from 0006's
sa.Column/FK conventions. `create_foreign_key` is passed `None` for its
constraint name (not a generated `op.f(...)` name): `app.db.base.Base`
declares no `naming_convention` on its metadata, so there is no
convention-derived name to reference; Postgres assigns its own default.

downgrade() drops the FK, the index, then the column, in that order. It does
NOT attempt to remove 'ai_category_suggested' from ticket_event_type --
Postgres has no ALTER TYPE ... DROP VALUE; the label stays defined but
simply becomes unused again.

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-01 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0008'
down_revision: Union[str, None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('tickets', sa.Column('ai_suggested_category_id', sa.Uuid(), nullable=True))
    op.create_index(
        op.f('ix_tickets_ai_suggested_category_id'),
        'tickets',
        ['ai_suggested_category_id'],
        unique=False,
    )
    op.create_foreign_key(
        'fk_tickets_ai_suggested_category_id_ticket_categories',
        'tickets',
        'ticket_categories',
        ['ai_suggested_category_id'],
        ['id'],
        ondelete='SET NULL',
    )
    op.execute("ALTER TYPE ticket_event_type ADD VALUE IF NOT EXISTS 'ai_category_suggested'")


def downgrade() -> None:
    op.drop_constraint(
        'fk_tickets_ai_suggested_category_id_ticket_categories', 'tickets', type_='foreignkey'
    )
    op.drop_index(op.f('ix_tickets_ai_suggested_category_id'), table_name='tickets')
    op.drop_column('tickets', 'ai_suggested_category_id')
