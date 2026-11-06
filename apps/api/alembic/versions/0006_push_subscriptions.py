"""Web push subscription storage (Phase 10).

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-05
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import NAMING_CONVENTION

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

NOW = sa.func.now()

metadata = sa.MetaData(naming_convention=NAMING_CONVENTION)

# Shadow of the existing users table so the FK below can resolve (Alembic
# pattern for migrations that reference a table created by an earlier one).
users = sa.Table(
    "users",
    metadata,
    sa.Column("id", UUID, primary_key=True),
)

push_subscriptions = sa.Table(
    "push_subscriptions",
    metadata,
    sa.Column("id", UUID, primary_key=True),
    sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    sa.Column("endpoint", sa.Text, nullable=False),
    sa.Column("p256dh", sa.String(255), nullable=False),
    sa.Column("auth", sa.String(255), nullable=False),
    sa.Column("user_agent", sa.String(500), nullable=True),
    sa.Column("last_pushed_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    sa.UniqueConstraint("endpoint", name="uq_push_subscriptions_endpoint"),
    sa.Index("ix_push_subscriptions_user_id", "user_id"),
)


def upgrade() -> None:
    # op.create_table only accepts a column list, so the full Table DDL is
    # emitted directly through the migration connection.
    push_subscriptions.create(op.get_bind(), checkfirst=False)


def downgrade() -> None:
    push_subscriptions.drop(op.get_bind())
