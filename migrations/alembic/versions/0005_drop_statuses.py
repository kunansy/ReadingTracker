"""Drop the statuses table, materials own started_at/completed_at.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID


revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_statuses_material_id", table_name="statuses")
    op.drop_table("statuses")


def downgrade() -> None:
    op.create_table(
        "statuses",
        sa.Column("status_id", UUID, primary_key=True),
        sa.Column("material_id", UUID, nullable=False),
        sa.Column("started_at", sa.DateTime, nullable=False),
        sa.Column("completed_at", sa.DateTime, nullable=True),
    )
    op.create_index(
        "ix_statuses_material_id",
        "statuses",
        ["material_id"],
        unique=True,
    )
    # Downgrade cannot restore the original status_id values.
    op.execute(
        "INSERT INTO statuses (status_id, material_id, started_at, completed_at) "
        "SELECT gen_random_uuid(), material_id, started_at, completed_at "
        "FROM materials WHERE started_at IS NOT NULL",
    )
