"""Index the keysets of the listings so a page is read from an index without sorting.

The partial index on materials.completed_at is replaced by a composite one with the same
leading column and predicate, which still serves the completion date ranges of the trends.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COMPLETED_AT_INDEX_NAME = "ix_materials_completed_at"
COMPLETED_AT_WHERE = "completed_at IS NOT NULL"
# the queue (started_at IS NULL) must keep reading the sort_key index
STARTED_AT_WHERE = "started_at IS NOT NULL"

READING_LOG_INDEX_NAME = "ix_reading_log_date_sort_key"
COMPLETED_INDEX_NAME = "ix_materials_completed_at_sort_key"
STARTED_INDEX_NAME = "ix_materials_started_at_sort_key"
LINKS_INDEX_NAME = "ix_notes_link_id_note_number_sort_key"


def upgrade() -> None:
    op.create_index(READING_LOG_INDEX_NAME, "reading_log", ["date", "sort_key"])
    op.create_index(
        COMPLETED_INDEX_NAME,
        "materials",
        ["completed_at", "sort_key"],
        postgresql_where=sa.text(COMPLETED_AT_WHERE),
    )
    op.drop_index(COMPLETED_AT_INDEX_NAME, table_name="materials")
    op.create_index(
        STARTED_INDEX_NAME,
        "materials",
        ["started_at", "sort_key"],
        postgresql_where=sa.text(STARTED_AT_WHERE),
    )
    op.create_index(LINKS_INDEX_NAME, "notes", ["link_id", "note_number", "sort_key"])


def downgrade() -> None:
    op.drop_index(LINKS_INDEX_NAME, table_name="notes")
    op.drop_index(STARTED_INDEX_NAME, table_name="materials")
    op.create_index(
        COMPLETED_AT_INDEX_NAME,
        "materials",
        ["completed_at"],
        postgresql_where=sa.text(COMPLETED_AT_WHERE),
    )
    op.drop_index(COMPLETED_INDEX_NAME, table_name="materials")
    op.drop_index(READING_LOG_INDEX_NAME, table_name="reading_log")
