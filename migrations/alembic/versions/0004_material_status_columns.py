"""Copy statuses.started_at/completed_at into materials.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from migrations.alembic.sql import REPEAT_NOTES_MATVIEW, REPEAT_NOTES_MATVIEW_V2


revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _recreate_matview(definition: str) -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mvw_repeat_notes")
    op.execute(definition)
    op.execute("REFRESH MATERIALIZED VIEW mvw_repeat_notes")


def upgrade() -> None:
    orphans = op.get_bind().scalar(
        sa.text(
            "SELECT count(*) FROM statuses s "
            "LEFT JOIN materials m USING (material_id) "
            "WHERE m.material_id IS NULL",
        ),
    )
    if orphans:
        msg = f"{orphans} statuses reference missing materials"
        raise RuntimeError(msg)

    op.add_column("materials", sa.Column("started_at", sa.DateTime, nullable=True))
    op.add_column("materials", sa.Column("completed_at", sa.DateTime, nullable=True))
    op.execute(
        "UPDATE materials m "
        "SET started_at = s.started_at, completed_at = s.completed_at "
        "FROM statuses s WHERE s.material_id = m.material_id",
    )
    _recreate_matview(REPEAT_NOTES_MATVIEW_V2)


def downgrade() -> None:
    _recreate_matview(REPEAT_NOTES_MATVIEW)
    op.drop_column("materials", "completed_at")
    op.drop_column("materials", "started_at")
