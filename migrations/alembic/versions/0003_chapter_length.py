"""Limit notes.chapter to 256 characters.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from migrations.alembic.sql import REPEAT_NOTES_MATVIEW


revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MAX_CHAPTER_LENGTH = 256
OLD_CHAPTER_LENGTH = 4096


def _set_chapter_type(length: int) -> None:
    # mvw_repeat_notes selects notes.chapter, Postgres refuses to retype it under a view.
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mvw_repeat_notes")
    op.alter_column("notes", "chapter", type_=sa.Unicode(length))
    op.execute(REPEAT_NOTES_MATVIEW)
    op.execute("REFRESH MATERIALIZED VIEW mvw_repeat_notes")


def upgrade() -> None:
    too_long = op.get_bind().scalar(
        sa.text("SELECT count(*) FROM notes WHERE char_length(chapter) > :limit"),
        {"limit": MAX_CHAPTER_LENGTH},
    )
    if too_long:
        msg = f"{too_long} notes have a chapter over {MAX_CHAPTER_LENGTH} characters"
        raise RuntimeError(msg)

    _set_chapter_type(MAX_CHAPTER_LENGTH)


def downgrade() -> None:
    _set_chapter_type(OLD_CHAPTER_LENGTH)
