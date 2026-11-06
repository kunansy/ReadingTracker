"""Add sort_key for keyset pagination.

Backfill expressions must match tracker/common/sort_keys.py.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("materials", "reading_log", "cards", "notes")

_DATETIME = "to_char({col}, 'YYYY-MM-DD\"T\"HH24:MI:SS.US')"
_CHAPTER_DIGITS = (
    "coalesce(nullif(ltrim(regexp_replace(chapter, '[^0-9]', '', 'g'), '0'), ''), '0')"
)


def _pad(expr: str) -> str:
    return f"CASE WHEN length({expr}) >= 10 THEN {expr} ELSE lpad({expr}, 10, '0') END"


BACKFILL = {
    "materials": f"{_DATETIME.format(col='added_at')} || '$$' || material_id::text",
    "reading_log": "to_char(date, 'YYYY-MM-DD') || '$$' || log_id::text",
    "cards": f"{_DATETIME.format(col='added_at')} || '$$' || card_id::text",
    "notes": (
        "material_id::text"
        f" || '$$' || {_pad(_CHAPTER_DIGITS)}"
        f" || '$$' || {_pad('page::text')}"
        " || '$$' || note_id::text"
    ),
}


def upgrade() -> None:
    for table in TABLES:
        op.add_column(
            table,
            sa.Column("sort_key", sa.Unicode(512, collation="C"), nullable=True),
        )
        op.execute(f"UPDATE {table} SET sort_key = {BACKFILL[table]}")  # noqa: S608
        op.alter_column(table, "sort_key", nullable=False)
        op.create_unique_constraint(f"{table}_sort_key_key", table, ["sort_key"])


def downgrade() -> None:
    for table in TABLES:
        op.drop_constraint(f"{table}_sort_key_key", table, type_="unique")
        op.drop_column(table, "sort_key")
