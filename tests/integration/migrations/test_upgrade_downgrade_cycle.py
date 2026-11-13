"""The real alembic commands, run over the whole revision chain."""

import datetime
import uuid

import pytest
import sqlalchemy.sql as sa

from tests.integration import factories, helpers
from tests.integration.migrations import helpers as migration_helpers
from tracker.common import sort_keys
from tracker.models import models


QUEUED = uuid.UUID("10000000-0000-4000-8000-000000000001")
READING = uuid.UUID("10000000-0000-4000-8000-000000000002")
COMPLETED = uuid.UUID("10000000-0000-4000-8000-000000000003")
ADDED_AT_0002 = uuid.UUID("10000000-0000-4000-8000-000000000004")
ADDED_AT_0005 = uuid.UUID("10000000-0000-4000-8000-000000000005")
NOTE = uuid.UUID("20000000-0000-4000-8000-000000000001")
NOTE_WITHOUT_TAGS = uuid.UUID("20000000-0000-4000-8000-000000000002")
NOTE_AT_0003 = uuid.UUID("20000000-0000-4000-8000-000000000003")
LOG = uuid.UUID("30000000-0000-4000-8000-000000000001")
CARD = uuid.UUID("40000000-0000-4000-8000-000000000001")
REPEAT = uuid.UUID("50000000-0000-4000-8000-000000000001")
NOTE_REPEAT = uuid.UUID("60000000-0000-4000-8000-000000000001")

ADDED_AT = datetime.datetime(2024, 1, 1, 10, 20, 30, 123456)  # noqa: DTZ001
STARTED_AT = datetime.datetime(2024, 1, 4)  # noqa: DTZ001
COMPLETED_AT = datetime.datetime(2024, 2, 5)  # noqa: DTZ001
LOG_DATE = datetime.date(2024, 1, 6)

TABLES_AT_HEAD = [
    "alembic_version",
    "cards",
    "materials",
    "note_repeats_history",
    "notes",
    "reading_log",
    "repeats",
]


async def _run(query: str, **params) -> None:
    await helpers.execute(sa.text(query), params)


async def _tables() -> list[str]:
    return sorted(await migration_helpers.schema_snapshot())


async def _material_at_0001(material_id: uuid.UUID, days: int) -> None:
    await _run(
        "INSERT INTO materials (material_id, title, authors, pages, material_type, added_at, "
        "is_outlined) VALUES (:id, :title, 'Автор', 100, 'book', :added_at, false)",
        id=material_id,
        title=f"Материал {material_id}",
        added_at=ADDED_AT + datetime.timedelta(days=days),
    )


async def _status(material_id: uuid.UUID, completed_at: datetime.datetime | None) -> None:
    await _run(
        "INSERT INTO statuses (status_id, material_id, started_at, completed_at) "
        "VALUES (gen_random_uuid(), :id, :started_at, :completed_at)",
        id=material_id,
        started_at=STARTED_AT,
        completed_at=completed_at,
    )


async def _seed_at_0001() -> None:
    for days, material_id in enumerate([QUEUED, READING, COMPLETED]):
        await _material_at_0001(material_id, days)
    await _status(READING, None)
    await _status(COMPLETED, COMPLETED_AT)
    await _run(
        "INSERT INTO notes (note_id, material_id, content, added_at, chapter, page, tags, "
        "is_deleted) VALUES (:id, :material_id, 'Заметка', :added_at, 'Глава 07', 3, "
        "CAST(:tags AS jsonb), false)",
        tags='["тег"]',
        id=NOTE,
        material_id=READING,
        added_at=ADDED_AT,
    )
    await _run(
        "INSERT INTO notes (note_id, material_id, content, added_at, chapter, page, tags, "
        "is_deleted) VALUES (:id, :material_id, 'No tags', :added_at, '', 0, NULL, true)",
        id=NOTE_WITHOUT_TAGS,
        material_id=COMPLETED,
        added_at=ADDED_AT,
    )
    await _run(
        "INSERT INTO reading_log (log_id, material_id, count, date) "
        "VALUES (:id, :material_id, 25, :date)",
        id=LOG,
        material_id=READING,
        date=LOG_DATE,
    )
    await _run(
        "INSERT INTO cards (card_id, material_id, note_id, question, answer, added_at) "
        "VALUES (:id, :material_id, :note_id, 'Q?', NULL, :added_at)",
        id=CARD,
        material_id=READING,
        note_id=NOTE,
        added_at=ADDED_AT,
    )
    await _run(
        "INSERT INTO repeats (repeat_id, material_id, repeated_at) "
        "VALUES (:id, :material_id, :repeated_at)",
        id=REPEAT,
        material_id=COMPLETED,
        repeated_at=COMPLETED_AT,
    )
    await _run(
        "INSERT INTO note_repeats_history (repeat_id, note_id, user_id, repeated_at) "
        "VALUES (:id, :note_id, 1, :repeated_at)",
        id=NOTE_REPEAT,
        note_id=NOTE,
        repeated_at=COMPLETED_AT,
    )


async def _sort_keys(table: str, id_column: str) -> dict[uuid.UUID, str]:
    rows = await helpers.fetch_all(f"SELECT {id_column}, sort_key FROM {table}")  # noqa: S608
    return {row[0]: row[1] for row in rows}


async def _statuses() -> dict[uuid.UUID, tuple]:
    rows = await helpers.fetch_all(
        "SELECT material_id, started_at, completed_at FROM statuses",
    )
    return {row[0]: (row[1], row[2]) for row in rows}


async def _material_dates() -> dict[uuid.UUID, tuple]:
    rows = await helpers.fetch_all(
        "SELECT material_id, started_at, completed_at FROM materials",
    )
    return {row[0]: (row[1], row[2]) for row in rows}


async def _matview_statuses() -> dict[uuid.UUID, str]:
    await factories.refresh_repeat_notes_matview()
    rows = await helpers.fetch_all(
        "SELECT note_id, material_status FROM mvw_repeat_notes",
    )
    return {row[0]: row[1] for row in rows}


async def test_upgrade_downgrade_cycle_on_an_empty_database():
    schema_at_head = await migration_helpers.schema_snapshot()

    try:
        await migration_helpers.alembic_downgrade("base")
        tables_at_base = await _tables()
        revision_at_base = await helpers.scalar("SELECT count(*) FROM alembic_version")

        await migration_helpers.alembic_upgrade("head")

        assert tables_at_base == ["alembic_version"]
        assert revision_at_base == 0
        assert await migration_helpers.current_revision() == migration_helpers.HEAD_REVISION
        assert await migration_helpers.schema_snapshot() == schema_at_head
        assert await _tables() == TABLES_AT_HEAD
        for table in models.metadata.sorted_tables:
            assert await factories.count_rows(table) == 0, table.name
    finally:
        await migration_helpers.reset_schema_to_head()


@pytest.mark.parametrize(
    "revision", ["0001", "0002", "0003", "0004", "0005", "0006", "0007"]
)
async def test_every_revision_can_be_reached_and_left_on_an_empty_database(revision):
    schema_at_head = await migration_helpers.schema_snapshot()

    try:
        await migration_helpers.alembic_downgrade(revision)
        reached = await migration_helpers.current_revision()
        await migration_helpers.alembic_upgrade("head")

        assert reached == revision
        assert await migration_helpers.schema_snapshot() == schema_at_head
    finally:
        await migration_helpers.reset_schema_to_head()


async def test_upgrade_downgrade_cycle_with_rows_seeded_at_every_revision():
    try:
        await migration_helpers.alembic_downgrade("base")

        await migration_helpers.alembic_upgrade("0001")
        await _seed_at_0001()

        await migration_helpers.alembic_upgrade("0002")
        assert await _sort_keys("materials", "material_id") == {
            material_id: sort_keys.material_sort_key(
                added_at=ADDED_AT + datetime.timedelta(days=days),
                material_id=material_id,
            )
            for days, material_id in enumerate([QUEUED, READING, COMPLETED])
        }
        assert await _sort_keys("notes", "note_id") == {
            NOTE: f"{READING}$$0000000007$$0000000003$${NOTE}",
            NOTE_WITHOUT_TAGS: f"{COMPLETED}$$0000000000$$0000000000$${NOTE_WITHOUT_TAGS}",
        }
        assert await _sort_keys("reading_log", "log_id") == {
            LOG: sort_keys.reading_log_sort_key(
                material_id=READING,
                date=LOG_DATE,
                log_id=LOG,
            ),
        }
        assert await _sort_keys("cards", "card_id") == {
            CARD: sort_keys.card_sort_key(added_at=ADDED_AT, card_id=CARD),
        }
        await _run(
            "INSERT INTO materials (material_id, title, authors, pages, material_type, "
            "added_at, is_outlined, sort_key) VALUES (:id, 'Added at 0002', 'A', 5, 'article', "
            ":added_at, true, :sort_key)",
            id=ADDED_AT_0002,
            added_at=ADDED_AT + datetime.timedelta(days=3),
            sort_key=sort_keys.material_sort_key(
                added_at=ADDED_AT + datetime.timedelta(days=3),
                material_id=ADDED_AT_0002,
            ),
        )
        await _status(ADDED_AT_0002, COMPLETED_AT)

        await migration_helpers.alembic_upgrade("0003")
        await _run(
            "INSERT INTO notes (note_id, material_id, content, added_at, chapter, page, tags, "
            "is_deleted, sort_key) VALUES (:id, :material_id, 'At 0003', :added_at, :chapter, 1, "
            "'[]', false, 'note-at-0003')",
            id=NOTE_AT_0003,
            material_id=QUEUED,
            added_at=ADDED_AT,
            chapter="9" * 256,
        )
        assert await _matview_statuses() == {NOTE_AT_0003: "queue"}

        await migration_helpers.alembic_upgrade("0004")
        expected_dates = {
            QUEUED: (None, None),
            READING: (STARTED_AT, None),
            COMPLETED: (STARTED_AT, COMPLETED_AT),
            ADDED_AT_0002: (STARTED_AT, COMPLETED_AT),
        }
        assert await _material_dates() == expected_dates
        assert await _matview_statuses() == {NOTE_AT_0003: "queue"}

        await migration_helpers.alembic_upgrade("0005")
        assert "statuses" not in await _tables()
        await _run(
            "INSERT INTO materials (material_id, title, authors, pages, material_type, "
            "added_at, is_outlined, started_at, sort_key) VALUES (:id, 'Added at 0005', 'A', 5, "
            "'book', :added_at, false, :started_at, :sort_key)",
            id=ADDED_AT_0005,
            added_at=ADDED_AT - datetime.timedelta(days=1),
            started_at=STARTED_AT,
            sort_key=sort_keys.material_sort_key(
                added_at=ADDED_AT - datetime.timedelta(days=1),
                material_id=ADDED_AT_0005,
            ),
        )
        expected_dates[ADDED_AT_0005] = (STARTED_AT, None)

        await migration_helpers.alembic_upgrade("head")
        assert await migration_helpers.current_revision() == migration_helpers.HEAD_REVISION
        assert await _material_dates() == expected_dates
        assert await factories.count_rows(models.Notes) == 3
        assert await factories.count_rows(models.ReadingLog) == 1
        assert await factories.count_rows(models.Cards) == 1
        assert await factories.count_rows(models.Repeats) == 1
        assert await factories.count_rows(models.NoteRepeatsHistory) == 1
        note = await factories.fetch_row(models.Notes, NOTE)
        assert (note["chapter"], note["tags"], note["note_number"]) == (
            "Глава 07",
            ["тег"],
            1,
        )
        assert (await factories.fetch_row(models.Notes, NOTE_WITHOUT_TAGS))[
            "tags"
        ] is None

        await migration_helpers.alembic_downgrade("0006")
        indexes = await helpers.fetch_all('SELECT material_id, "index" FROM materials')
        assert {row[0]: row[1] for row in indexes} == {
            ADDED_AT_0005: 1,
            QUEUED: 2,
            READING: 3,
            COMPLETED: 4,
            ADDED_AT_0002: 5,
        }

        await migration_helpers.alembic_downgrade("0004")
        expected_statuses = {
            material_id: dates
            for material_id, dates in expected_dates.items()
            if dates[0] is not None
        }
        assert await _statuses() == expected_statuses
        assert await _material_dates() == expected_dates

        await migration_helpers.alembic_downgrade("0003")
        assert await _statuses() == expected_statuses
        assert await _matview_statuses() == {NOTE_AT_0003: "queue"}

        await migration_helpers.alembic_downgrade("0002")
        assert (await factories.fetch_row(models.Notes, NOTE_AT_0003))[
            "chapter"
        ] == "9" * 256

        await migration_helpers.alembic_downgrade("0001")
        assert await helpers.scalar("SELECT count(*) FROM materials") == 5
        assert await helpers.scalar("SELECT count(*) FROM notes") == 3
        assert await helpers.scalar("SELECT count(*) FROM statuses") == 4

        await migration_helpers.alembic_upgrade("head")
        assert await _material_dates() == expected_dates
        assert (await _sort_keys("notes", "note_id"))[NOTE_AT_0003] == (
            f"{QUEUED}$${'9' * 256}$$0000000001$${NOTE_AT_0003}"
        )

        await migration_helpers.alembic_downgrade("base")
        assert await _tables() == ["alembic_version"]
    finally:
        await migration_helpers.reset_schema_to_head()


async def test_upgrade_to_0003_stops_on_a_long_chapter_and_keeps_the_revision():
    try:
        await migration_helpers.alembic_downgrade("0002")
        await _run(
            "INSERT INTO notes (note_id, material_id, content, added_at, chapter, page, "
            "is_deleted, sort_key) VALUES (:id, :material_id, 'Long', :added_at, :chapter, 1, "
            "false, 'long')",
            id=NOTE,
            material_id=QUEUED,
            added_at=ADDED_AT,
            chapter="1" * 257,
        )

        with pytest.raises(
            RuntimeError,
            match="1 notes have a chapter over 256 characters",
        ):
            await migration_helpers.alembic_upgrade("head")

        assert await migration_helpers.current_revision() == "0002"
        assert await helpers.scalar("SELECT char_length(chapter) FROM notes") == 257

        await _run("UPDATE notes SET chapter = '1'")
        await migration_helpers.alembic_upgrade("head")
        assert await migration_helpers.current_revision() == migration_helpers.HEAD_REVISION
    finally:
        await migration_helpers.reset_schema_to_head()
