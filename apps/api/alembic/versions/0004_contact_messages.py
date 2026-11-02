"""Contact messages from the public landing page (Phase 7).

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-03
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.models.base import NAMING_CONVENTION

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
NOW = sa.func.now()

metadata = sa.MetaData(naming_convention=NAMING_CONVENTION)

contact_messages = sa.Table(
    "contact_messages",
    metadata,
    sa.Column("id", UUID, primary_key=True),
    sa.Column("name", sa.String(255), nullable=False),
    sa.Column("email", sa.String(255), nullable=False),
    sa.Column("organisation", sa.String(255), nullable=True),
    sa.Column("role", sa.String(32), nullable=False),
    sa.Column("message", sa.Text(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
)
sa.Index("ix_contact_messages_email", contact_messages.c.email)


def upgrade() -> None:
    # op.create_table only accepts a column list, so the full Table DDL is
    # emitted directly through the migration connection.
    contact_messages.create(op.get_bind(), checkfirst=False)


def downgrade() -> None:
    op.drop_table("contact_messages")
