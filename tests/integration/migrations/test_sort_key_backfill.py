"""The SQL backfill of revision 0002 must produce the keys tracker.common.sort_keys builds."""

import datetime
import uuid

import pytest
import sqlalchemy.sql as sa

from tests.integration import helpers_notes as helpers
from tests.integration.migrations.revisions import REVISION_0002
from tracker.common import sort_keys


BACKFILL: dict[str, str] = REVISION_0002.BACKFILL
MATERIAL_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
ROW_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")


async def _backfill(table: str, columns: str, **params: object) -> str:
    query = f"SELECT {BACKFILL[table]} FROM (SELECT {columns}) AS t"  # noqa: S608
    return await helpers.scalar(query, **params)


def test_backfill_covers_every_table_with_a_sort_key():
    assert (
        set(BACKFILL)
        == set(REVISION_0002.TABLES)
        == {
            "materials",
            "reading_log",
            "cards",
            "notes",
        }
    )


@pytest.mark.parametrize(
    "added_at",
    [
        datetime.datetime(2024, 1, 2, 3, 4, 5),  # noqa: DTZ001
        datetime.datetime(2024, 1, 2, 3, 4, 5, 6),  # noqa: DTZ001
        datetime.datetime(1999, 12, 31, 23, 59, 59, 999_999),  # noqa: DTZ001
    ],
    ids=["no-fraction", "microseconds", "max-fraction"],
)
@pytest.mark.parametrize(
    ("table", "id_column", "build"),
    [
        (
            "materials",
            "material_id",
            lambda added_at: sort_keys.material_sort_key(
                added_at=added_at,
                material_id=ROW_ID,
            ),
        ),
        (
            "cards",
            "card_id",
            lambda added_at: sort_keys.card_sort_key(
                added_at=added_at,
                card_id=ROW_ID,
            ),
        ),
    ],
    ids=["materials", "cards"],
)
async def test_datetime_keyed_backfill_matches_python(table, id_column, build, added_at):
    result = await _backfill(
        table,
        f"CAST(:added_at AS timestamp) AS added_at, CAST(:id AS uuid) AS {id_column}",
        added_at=added_at,
        id=ROW_ID,
    )

    assert result == build(added_at)


@pytest.mark.parametrize(
    "date",
    [datetime.date(2024, 1, 2), datetime.date(2024, 12, 31), datetime.date(999, 1, 1)],
    ids=["january", "december", "three-digit-year"],
)
async def test_reading_log_backfill_matches_python(date):
    result = await _backfill(
        "reading_log",
        "CAST(:material_id AS uuid) AS material_id, CAST(:date AS date) AS date,"
        " CAST(:log_id AS uuid) AS log_id",
        material_id=MATERIAL_ID,
        date=date,
        log_id=ROW_ID,
    )

    assert result == sort_keys.reading_log_sort_key(
        material_id=MATERIAL_ID,
        date=date,
        log_id=ROW_ID,
    )


NOTE_CASES = [
    (None, 0),
    ("", 1),
    ("abc", 2),
    ("007", 3),
    ("Глава 12", 4),
    ("1.2", 5),
    ("12345678901", 6),
    ("1", 2_147_483_647),
    ("000", 7),
    ("٣", 8),
    ("1" * 256, 9),
]


@pytest.mark.parametrize(
    ("chapter", "page"),
    NOTE_CASES,
    ids=[
        "null-chapter",
        "empty",
        "letters",
        "leading-zeros",
        "cyrillic",
        "dotted",
        "eleven-digits",
        "max-page",
        "only-zeros",
        "non-ascii-digit",
        "max-length",
    ],
)
async def test_notes_backfill_matches_python(chapter, page):
    result = await _backfill(
        "notes",
        "CAST(:material_id AS uuid) AS material_id, CAST(:chapter AS text) AS chapter,"
        " CAST(:page AS integer) AS page, CAST(:note_id AS uuid) AS note_id",
        material_id=MATERIAL_ID,
        chapter=chapter,
        page=page,
        note_id=ROW_ID,
    )

    assert result == sort_keys.note_sort_key(
        material_id=MATERIAL_ID,
        chapter=chapter,
        page=page,
        note_id=ROW_ID,
    )


async def test_notes_backfill_pads_a_negative_page_differently_current_behaviour():
    result = await _backfill(
        "notes",
        "CAST(:material_id AS uuid) AS material_id, CAST('1' AS text) AS chapter,"
        " CAST(-5 AS integer) AS page, CAST(:note_id AS uuid) AS note_id",
        material_id=MATERIAL_ID,
        note_id=ROW_ID,
    )

    # the API schema forbids negative pages, the column does not
    assert result == f"{MATERIAL_ID}$$0000000001$$00000000-5$${ROW_ID}"
    assert (
        sort_keys.note_sort_key(
            material_id=MATERIAL_ID,
            chapter="1",
            page=-5,
            note_id=ROW_ID,
        )
        == f"{MATERIAL_ID}$$0000000001$$-000000005$${ROW_ID}"
    )


def test_backfill_is_plain_text_sql():
    for expression in BACKFILL.values():
        sa.text(expression)
        assert ";" not in expression
