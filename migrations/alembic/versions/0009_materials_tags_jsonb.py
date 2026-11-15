r"""Store material and note tags as a non-null JSONB list.

Material tags were a comma separated string, note tags a nullable JSONB value. Both are
normalized the same way, so every tag matches the API tag rules: each tag is trimmed and
lowercased, every run of non-word characters becomes `_`, it is cut to 128 characters and
stripped of `_` at both ends. Empty tags are dropped, the rest are deduplicated, sorted by
code point, and only the first 32 are kept. SQL NULL and non-array note tags become `[]`.
Whitespace around material title, authors and link is trimmed. The downgrade joins
material tags back with ", " and makes both columns nullable again; the `[]` note tags
stay as they are.

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
MAX_TAG_LENGTH = 128
MAX_TAGS = 32

NORMALIZE_TAG_FUNCTION = rf"""
CREATE OR REPLACE FUNCTION pg_temp.normalize_tag(raw text) RETURNS text
LANGUAGE sql IMMUTABLE AS $$
    SELECT trim(BOTH '_' FROM
        left(regexp_replace(lower(trim(raw)), '\W+', '_', 'g'), {MAX_TAG_LENGTH}))
$$
"""  # noqa: S608


def _tags_to_jsonb(name: str, argument: str, source: str) -> str:
    return f"""
CREATE OR REPLACE FUNCTION pg_temp.{name}(tags {argument}) RETURNS jsonb
LANGUAGE sql IMMUTABLE AS $$
    SELECT coalesce(jsonb_agg(tag ORDER BY tag COLLATE "C"), '[]'::jsonb)
    FROM (
        SELECT tag
        FROM (SELECT DISTINCT pg_temp.normalize_tag(raw) AS tag FROM {source} AS raw) AS t
        WHERE tag <> ''
        ORDER BY tag COLLATE "C"
        LIMIT {MAX_TAGS}
    ) AS normalized
$$
"""  # noqa: S608


# ALTER COLUMN ... USING does not accept a subquery, so it calls a function
TO_JSONB_FUNCTION = _tags_to_jsonb(
    "material_tags_to_jsonb",
    "text",
    "regexp_split_to_table(tags, ',')",
)

NORMALIZE_NOTE_TAGS_FUNCTION = _tags_to_jsonb(
    "normalize_note_tags",
    "jsonb",
    "jsonb_array_elements_text("
    "CASE WHEN jsonb_typeof(tags) = 'array' THEN tags ELSE '[]'::jsonb END)",
)

TO_TEXT_FUNCTION = """
CREATE OR REPLACE FUNCTION pg_temp.material_tags_to_text(tags jsonb) RETURNS text
LANGUAGE sql IMMUTABLE AS $$
    SELECT nullif(string_agg(tag, ', ' ORDER BY tag COLLATE "C"), '')
    FROM jsonb_array_elements_text(tags) AS tag
$$
"""

TRIM_MATERIAL_STRINGS = r"""
UPDATE materials SET
    title = btrim(title, E' \t\n\r\v\f'),
    authors = btrim(authors, E' \t\n\r\v\f'),
    link = btrim(link, E' \t\n\r\v\f')
"""


def upgrade() -> None:
    op.execute(TRIM_MATERIAL_STRINGS)
    op.execute(NORMALIZE_TAG_FUNCTION)
    op.execute(TO_JSONB_FUNCTION)
    op.alter_column(
        "materials",
        "tags",
        type_=JSONB,
        existing_type=sa.Unicode(256),
        existing_nullable=True,
        postgresql_using="pg_temp.material_tags_to_jsonb(tags)",
    )
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
