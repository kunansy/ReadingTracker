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

from migrations.alembic.sql import REPEAT_NOTES_MATVIEW


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
