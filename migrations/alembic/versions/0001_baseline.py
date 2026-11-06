"""Baseline: schema as created by metadata.create_all before Alembic.

Existing databases are stamped with this revision instead of running it.

Revision ID: 0001
Revises:
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql.type_api import UserDefinedType


revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


class _Serial(UserDefinedType):
    cache_ok = True

    def get_col_spec(self, **kw) -> str:  # noqa: ARG002
        return "serial"


def _pk(name: str) -> sa.Column:
    return sa.Column(name, UUID, primary_key=True, nullable=False)


REPEAT_NOTES_MATVIEW = """
    CREATE MATERIALIZED VIEW IF NOT EXISTS mvw_repeat_notes AS
        WITH sample_notes AS (
            SELECT
                n.note_id,
                n.material_id,
                n.page,
                n.chapter,
                n.title,
                n.content,
                n.added_at,
                n.tags,
                COUNT(1) OVER () AS total_notes_count
            FROM notes n
            WHERE NOT n.is_deleted
        ),
        last_material_repeat AS (
            SELECT
                r.material_id,
                max(r.repeated_at) AS repeated_at,
                COUNT(1) AS repeats_count
            FROM repeats r
            GROUP BY r.material_id
        ),
        last_note_repeat_date AS (
            SELECT
                max(rh.repeated_at::date) as date,
                n.note_id
            FROM
                note_repeats_history rh
            FULL OUTER JOIN
                notes n ON n.note_id = rh.note_id
            WHERE
                n is null or not n.is_deleted
            GROUP BY n.note_id
        ), oldest_notes AS (
            SELECT
                DATE_TRUNC('month', lrd.date) as date,
                ARRAY_AGG(lrd.note_id) AS notes
            FROM
                last_note_repeat_date lrd
            GROUP BY
                date
            ORDER BY
                date NULLS FIRST, COUNT(1)
            LIMIT 1
        )
        SELECT
            n.note_id,
            m.material_id,
            m.title AS material_title,
            m.authors AS material_authors,
            m.material_type AS material_type,
            n.content,
            n.added_at,
            n.chapter,
            n.page,
            n.tags,
            m.pages AS material_pages,
            n.total_notes_count AS total_notes_count,
            0 AS min_repeat_freq,
            CASE
                -- in this case the note have no material
                WHEN m IS NULL THEN 'completed'
                WHEN s IS NULL THEN 'queue'
                WHEN s.completed_at IS NULL THEN 'reading'
                ELSE 'completed'
            END AS material_status,
            r.repeated_at,
            r.repeats_count
        FROM
            sample_notes n
        JOIN oldest_notes ON n.note_id = ANY(oldest_notes.notes)
        LEFT JOIN materials m ON n.material_id = m.material_id
        LEFT JOIN statuses s ON s.material_id = m.material_id
        LEFT JOIN last_material_repeat r ON r.material_id = s.material_id
    WITH NO DATA;
    """


def upgrade() -> None:
    op.create_table(
        "materials",
        _pk("material_id"),
        sa.Column("title", sa.Unicode(256), nullable=False),
        sa.Column("authors", sa.Unicode(256), nullable=False),
        sa.Column("pages", sa.Integer, nullable=False),
        sa.Column("material_type", sa.Unicode(50), nullable=False),
        sa.Column("tags", sa.Unicode(256), nullable=True),
        sa.Column("link", sa.Unicode(2048), nullable=True),
        sa.Column("added_at", sa.DateTime, nullable=False),
        sa.Column("is_outlined", sa.Boolean, nullable=False),
        sa.Column("index", _Serial, nullable=False),
        sa.UniqueConstraint("title", "material_type", name="uix_material"),
        sa.UniqueConstraint("index", name="uix_materials_index", deferrable=True),
    )
    op.create_table(
        "reading_log",
        _pk("log_id"),
        sa.Column("material_id", UUID, nullable=False),
        sa.Column("count", sa.Integer, nullable=False),
        sa.Column("date", sa.Date, nullable=False),
        sa.UniqueConstraint("material_id", "date", name="uix_reading_log"),
    )
    op.create_index("ix_reading_log_material_id", "reading_log", ["material_id"])
    op.create_table(
        "statuses",
        _pk("status_id"),
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
    op.create_table(
        "notes",
        _pk("note_id"),
        sa.Column("note_number", _Serial, nullable=False),
        sa.Column("material_id", UUID, nullable=False),
        sa.Column("link_id", UUID, nullable=True, comment="By Zettelkasten method"),
        sa.Column("title", sa.Unicode(4096), nullable=True, unique=True),
        sa.Column("content", sa.Unicode(65_536), nullable=False),
        sa.Column("added_at", sa.DateTime, nullable=False),
        sa.Column("chapter", sa.Unicode(4096), nullable=False),
        sa.Column("page", sa.Integer, nullable=False),
        sa.Column("tags", JSONB, nullable=True),
        sa.Column("is_deleted", sa.Boolean, nullable=False),
        sa.UniqueConstraint(
            "note_number",
            name="uix_notes_note_number",
            deferrable=True,
        ),
    )
    op.create_index("ix_notes_material_id", "notes", ["material_id"])
    op.create_table(
        "cards",
        _pk("card_id"),
        sa.Column("material_id", UUID, nullable=False),
        sa.Column("note_id", UUID, nullable=False),
        sa.Column("question", sa.Unicode, nullable=False),
        sa.Column("answer", sa.Unicode, nullable=True),
        sa.Column("added_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_cards_material_id", "cards", ["material_id"])
    op.create_index("ix_cards_note_id", "cards", ["note_id"])
    op.create_table(
        "repeats",
        _pk("repeat_id"),
        sa.Column("material_id", UUID, nullable=False),
        sa.Column("repeated_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_repeats_material_id", "repeats", ["material_id"])
    op.create_table(
        "note_repeats_history",
        _pk("repeat_id"),
        sa.Column("note_id", UUID, nullable=False),
        sa.Column("user_id", sa.BigInteger, nullable=False, comment="Telegram user id"),
        sa.Column("repeated_at", sa.DateTime, nullable=False),
    )
    op.create_index(
        "ix_note_repeats_history_note_id",
        "note_repeats_history",
        ["note_id"],
    )
    op.execute(REPEAT_NOTES_MATVIEW)


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mvw_repeat_notes")
    for table in (
        "note_repeats_history",
        "repeats",
        "cards",
        "notes",
        "statuses",
        "reading_log",
        "materials",
    ):
        op.drop_table(table)
