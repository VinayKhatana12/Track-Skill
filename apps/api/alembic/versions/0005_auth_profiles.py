"""Auth profile support: centre codes + nullable trainee centre/course (Phase 8).

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-03
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Centre codes for self-registered trainees ("if enrolled, enter the
    # centre code").
    op.add_column(
        "training_centres",
        sa.Column("code", sa.String(32), nullable=True),
    )
    conn = op.get_bind()
    centres = conn.execute(
        sa.text("SELECT id FROM training_centres ORDER BY created_at")
    ).fetchall()
    for index, row in enumerate(centres, start=1):
        conn.execute(
            sa.text("UPDATE training_centres SET code = :code WHERE id = :id"),
            {"code": f"TC-{index:02d}", "id": row.id},
        )
    op.alter_column("training_centres", "code", existing_type=sa.String(32), nullable=False)
    op.create_unique_constraint(
        "uq_training_centres_code", "training_centres", ["code"]
    )

    # Self-registered trainees may not be attached to a centre or course yet.
    op.alter_column(
        "trainees",
        "centre_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )
    op.alter_column(
        "trainees",
        "course_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM trainees WHERE centre_id IS NULL OR course_id IS NULL")
    )
    op.alter_column(
        "trainees",
        "course_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.alter_column(
        "trainees",
        "centre_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.drop_constraint("uq_training_centres_code", "training_centres", type_="unique")
    op.drop_column("training_centres", "code")
