"""Baseline revision: establishes Alembic tracking for TrackSkill AI.

Revision ID: 0001
Revises:
Create Date: 2026-10-31
"""

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """No schema yet — the first domain tables arrive with the data-model phase."""


def downgrade() -> None:
    """Nothing to undo for the baseline."""
