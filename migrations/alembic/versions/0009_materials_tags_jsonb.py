r"""Store material and note tags as a non-null JSONB list.

Material tags were a comma separated string: it is split, trimmed and lowercased, and
every run of non-word characters becomes `_`, so each tag matches the API tag pattern.
Note tags were already JSONB, but nullable: SQL NULL and any non-array value become `[]`,
and arrays are trimmed, lowercased, deduplicated and sorted the way the API stores them.
Whitespace around material strings is trimmed once here, so reads do not strip it any
more. The downgrade joins material tags back with ", " and makes both columns nullable
again; the `[]` note tags stay as they are.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMPTY_TAGS = sa.text("'[]'::jsonb")

# ALTER COLUMN ... USING does not accept a subquery, so it calls a function
TO_JSONB_FUNCTION = """
CREATE OR REPLACE FUNCTION pg_temp.material_tags_to_jsonb(tags text) RETURNS jsonb
LANGUAGE sql IMMUTABLE AS $$
    SELECT coalesce(jsonb_agg(tag ORDER BY tag), '[]'::jsonb)
    FROM (
        SELECT DISTINCT
            trim(BOTH '_' FROM regexp_replace(lower(trim(raw)), '\\W+', '_', 'g')) AS tag
        FROM regexp_split_to_table(tags, ',') AS raw
    ) AS normalized
    WHERE tag <> ''
$$
"""

TO_TEXT_FUNCTION = """
CREATE OR REPLACE FUNCTION pg_temp.material_tags_to_text(tags jsonb) RETURNS text
LANGUAGE sql IMMUTABLE AS $$
    SELECT nullif(string_agg(tag, ', ' ORDER BY tag), '')
    FROM jsonb_array_elements_text(tags) AS tag
$$
"""

TRIM_MATERIAL_STRINGS = r"""
UPDATE materials SET
    title = btrim(title, E' \t\n\r\v\f'),
    authors = btrim(authors, E' \t\n\r\v\f'),
    link = btrim(link, E' \t\n\r\v\f')
"""

NORMALIZE_NOTE_TAGS_FUNCTION = """
CREATE OR REPLACE FUNCTION pg_temp.normalize_note_tags(tags jsonb) RETURNS jsonb
LANGUAGE sql IMMUTABLE AS $$
    SELECT coalesce(jsonb_agg(DISTINCT tag ORDER BY tag), '[]'::jsonb)
    FROM jsonb_array_elements_text(
        CASE WHEN jsonb_typeof(tags) = 'array' THEN tags ELSE '[]'::jsonb END
    ) AS raw, lower(trim(raw)) AS tag
    WHERE tag <> ''
$$
"""


def upgrade() -> None:
    op.execute(TRIM_MATERIAL_STRINGS)
    op.execute(TO_JSONB_FUNCTION)
    op.alter_column(
        "materials",
        "tags",
        type_=JSONB,
        existing_type=sa.Unicode(256),
        existing_nullable=True,
        postgresql_using="pg_temp.material_tags_to_jsonb(tags)",
    )
    op.execute("UPDATE materials SET tags = '[]'::jsonb WHERE tags IS NULL")
    op.alter_column(
        "materials",
        "tags",
        existing_type=JSONB,
        nullable=False,
        server_default=EMPTY_TAGS,
    )

    op.execute(NORMALIZE_NOTE_TAGS_FUNCTION)
    op.execute("UPDATE notes SET tags = pg_temp.normalize_note_tags(tags)")
    op.alter_column(
        "notes",
        "tags",
        existing_type=JSONB,
        nullable=False,
        server_default=EMPTY_TAGS,
    )


def downgrade() -> None:
    op.alter_column(
        "notes",
        "tags",
        existing_type=JSONB,
        nullable=True,
        server_default=None,
    )

    op.execute(TO_TEXT_FUNCTION)
    op.alter_column(
        "materials",
        "tags",
        existing_type=JSONB,
        nullable=True,
        server_default=None,
    )
    op.alter_column(
        "materials",
        "tags",
        type_=sa.Unicode(256),
        existing_type=JSONB,
        existing_nullable=True,
        postgresql_using="pg_temp.material_tags_to_text(tags)",
    )
