import datetime
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Connection

from tests.integration.migrations import revisions
from tests.integration.migrations.revisions import (
    REVISION_0002,
    REVISION_0003,
    REVISION_0004,
    REVISION_0005,
    REVISION_0006,
    REVISION_0007,
    REVISION_0008,
    in_rolled_back_migration,
)
from tracker.common import sort_keys
from tracker.models import enums, models


ADDED_AT = datetime.datetime(2024, 1, 1)  # noqa: DTZ001
STARTED_AT = datetime.datetime(2024, 1, 4)  # noqa: DTZ001
COMPLETED_AT = datetime.datetime(2024, 2, 5)  # noqa: DTZ001

MATERIAL_STATUSES = sa.text(
    "SELECT material_id, started_at, completed_at FROM materials "
    "WHERE started_at IS NOT NULL ORDER BY material_id",
)
LEGACY_STATUSES = sa.text(
    "SELECT material_id, started_at, completed_at FROM statuses ORDER BY material_id",
)
MATVIEW_STATUSES = sa.text(
    "SELECT material_status, count(*) FROM mvw_repeat_notes "
    "GROUP BY material_status ORDER BY material_status",
)


def _rows(conn: Connection, query: sa.TextClause) -> list[tuple]:
    return [tuple(row) for row in conn.execute(query).all()]


def _insert_material(
    conn: Connection,
    *,
    started_at: datetime.datetime | None = None,
    completed_at: datetime.datetime | None = None,
    added_at: datetime.datetime = ADDED_AT,
) -> uuid.UUID:
    material_id = uuid.uuid4()
    conn.execute(
        models.Materials.insert().values(
            material_id=material_id,
            title=f"Material {material_id}",
            authors="Author",
            pages=10,
            material_type=enums.MaterialTypesEnum.book,
            added_at=added_at,
            is_outlined=False,
            started_at=started_at,
            completed_at=completed_at,
            sort_key=sort_keys.material_sort_key(
                added_at=added_at,
                material_id=material_id,
            ),
        ),
    )
    return material_id


def _insert_note(
    conn: Connection,
    *,
    material_id: uuid.UUID,
    chapter: str = "1",
) -> uuid.UUID:
    note_id = uuid.uuid4()
    conn.execute(
        models.Notes.insert().values(
            note_id=note_id,
            material_id=material_id,
            content="Migration note.",
            chapter=chapter,
            page=1,
            tags=[],
            sort_key=sort_keys.note_sort_key(
                material_id=material_id,
                chapter=chapter,
                page=1,
                note_id=note_id,
            ),
        ),
    )
    return note_id


def _seed_materials(conn: Connection) -> dict[str, tuple]:
    """A queued, a reading and a completed material with one note each, keyed by state."""
    states = {
        "queued": (None, None),
        "reading": (STARTED_AT, None),
        "completed": (STARTED_AT, COMPLETED_AT),
    }
    seeded = {}
    for state, (started_at, completed_at) in states.items():
        material_id = _insert_material(
            conn,
            started_at=started_at,
            completed_at=completed_at,
        )
        _insert_note(conn, material_id=material_id)
        seeded[state] = (material_id, started_at, completed_at)
    return seeded


def _chapter_length(conn: Connection) -> int:
    return conn.scalar(
        sa.text(
            "SELECT character_maximum_length FROM information_schema.columns "
            "WHERE table_name = 'notes' AND column_name = 'chapter'",
        ),
    )


def _has_matview(conn: Connection) -> bool:
    return conn.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM pg_matviews WHERE matviewname = 'mvw_repeat_notes')",
        ),
    )


def _columns(conn: Connection, table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(conn).get_columns(table)}


async def test_0003_downgrade_restores_the_old_chapter_length():
    def check(conn: Connection) -> tuple[int, bool]:
        revisions.downgrade_to(REVISION_0002)
        return _chapter_length(conn), _has_matview(conn)

    assert await in_rolled_back_migration(check) == (
        REVISION_0003.OLD_CHAPTER_LENGTH,
        True,
    )


async def test_0003_upgrade_refuses_a_chapter_over_the_limit():
    def check(conn: Connection) -> int:
        revisions.downgrade_to(REVISION_0002)
        material_id = uuid.uuid4()
        conn.execute(
            sa.text(
                "INSERT INTO notes (note_id, material_id, content, added_at, chapter, page, "
                "is_deleted, sort_key) VALUES (gen_random_uuid(), :material_id, 'Note', "
                ":added_at, :chapter, 1, false, 'key')",
            ),
            {
                "material_id": material_id,
                "added_at": ADDED_AT,
                "chapter": "1" * (REVISION_0003.MAX_CHAPTER_LENGTH + 1),
            },
        )

        with pytest.raises(
            RuntimeError,
            match="1 notes have a chapter over 256 characters",
        ):
            REVISION_0003.upgrade()
        return _chapter_length(conn)

    assert await in_rolled_back_migration(check) == REVISION_0003.OLD_CHAPTER_LENGTH


async def test_0003_upgrade_keeps_a_chapter_exactly_at_the_limit():
    chapter = "я" * REVISION_0003.MAX_CHAPTER_LENGTH

    def check(conn: Connection) -> tuple[int, bool, str]:
        revisions.downgrade_to(REVISION_0002)
        conn.execute(
            sa.text(
                "INSERT INTO notes (note_id, material_id, content, added_at, chapter, page, "
                "is_deleted, sort_key) VALUES (gen_random_uuid(), gen_random_uuid(), 'Note', "
                ":added_at, :chapter, 1, false, 'key')",
            ),
            {"added_at": ADDED_AT, "chapter": chapter},
        )

        REVISION_0003.upgrade()
        return (
            _chapter_length(conn),
            _has_matview(conn),
            conn.scalar(sa.text("SELECT chapter FROM notes")),
        )

    assert await in_rolled_back_migration(check) == (
        REVISION_0003.MAX_CHAPTER_LENGTH,
        True,
        chapter,
    )


async def test_0003_upgrade_on_an_empty_table_leaves_a_populated_matview():
    def check(conn: Connection) -> tuple[int, bool]:
        revisions.downgrade_to(REVISION_0002)
        REVISION_0003.upgrade()
        populated = conn.scalar(
            sa.text(
                "SELECT ispopulated FROM pg_matviews WHERE matviewname = 'mvw_repeat_notes'",
            ),
        )
        return _chapter_length(conn), populated

    assert await in_rolled_back_migration(check) == (
        REVISION_0003.MAX_CHAPTER_LENGTH,
        True,
    )


def test_0003_limit_matches_the_model():
    assert REVISION_0003.MAX_CHAPTER_LENGTH == models.MAX_CHAPTER_LENGTH
    assert models.Notes.c.chapter.type.length == models.MAX_CHAPTER_LENGTH


async def test_0005_and_0004_downgrade_restore_statuses_from_materials():
    def check(conn: Connection) -> tuple:
        seeded = _seed_materials(conn)
        revisions.downgrade_to(REVISION_0003)
        status_ids = tuple(
            conn.execute(
                sa.text("SELECT count(*), count(DISTINCT status_id) FROM statuses"),
            ).one(),
        )
        return (
            seeded,
            _rows(conn, LEGACY_STATUSES),
            status_ids,
            _columns(conn, "materials"),
        )

    seeded, restored, status_ids, columns = await in_rolled_back_migration(check)

    assert restored == sorted([seeded["reading"], seeded["completed"]])
    assert status_ids == (2, 2)
    assert {"started_at", "completed_at"}.isdisjoint(columns)


async def test_0004_and_0005_round_trip_keeps_statuses_and_the_matview():
    def check(conn: Connection) -> tuple:
        seeded = _seed_materials(conn)
        conn.execute(sa.text("REFRESH MATERIALIZED VIEW mvw_repeat_notes"))
        matview_before = _rows(conn, MATVIEW_STATUSES)

        revisions.downgrade_to(REVISION_0003)
        legacy_matview = _rows(conn, MATVIEW_STATUSES)
        REVISION_0004.upgrade()
        REVISION_0005.upgrade()

        return (
            seeded,
            _rows(conn, MATERIAL_STATUSES),
            matview_before,
            legacy_matview,
            _rows(conn, MATVIEW_STATUSES),
            sa.inspect(conn).has_table("statuses"),
        )

    (
        seeded,
        statuses_after,
        matview_before,
        legacy_matview,
        matview_after,
        has_statuses,
    ) = await in_rolled_back_migration(check)

    expected_matview = [("completed", 1), ("queue", 1), ("reading", 1)]
    assert statuses_after == sorted([seeded["reading"], seeded["completed"]])
    assert matview_before == legacy_matview == matview_after == expected_matview
    assert has_statuses is False


async def test_0004_upgrade_on_empty_tables_adds_the_columns():
    def check(conn: Connection) -> tuple[set[str], list[tuple]]:
        revisions.downgrade_to(REVISION_0003)
        REVISION_0004.upgrade()
        return _columns(conn, "materials"), _rows(conn, MATVIEW_STATUSES)

    columns, matview = await in_rolled_back_migration(check)

    assert {"started_at", "completed_at"} <= columns
    assert matview == []


async def test_0004_upgrade_aborts_on_a_status_without_a_material():
    def check(conn: Connection) -> set[str]:
        revisions.downgrade_to(REVISION_0003)
        conn.execute(
            sa.text(
                "INSERT INTO statuses (status_id, material_id, started_at) "
                "VALUES (gen_random_uuid(), gen_random_uuid(), :started_at)",
            ),
            {"started_at": STARTED_AT},
        )

        with pytest.raises(RuntimeError, match="1 statuses reference missing materials"):
            REVISION_0004.upgrade()

        return _columns(conn, "materials")

    columns = await in_rolled_back_migration(check)

    assert {"started_at", "completed_at"}.isdisjoint(columns)


async def test_0005_downgrade_drops_a_completion_without_a_start_current_behaviour():
    def check(conn: Connection) -> tuple[list[tuple], list[tuple]]:
        _insert_material(conn, started_at=None, completed_at=COMPLETED_AT)
        revisions.downgrade_to(REVISION_0003)
        REVISION_0004.upgrade()
        return _rows(conn, LEGACY_STATUSES), _rows(
            conn,
            sa.text("SELECT started_at, completed_at FROM materials"),
        )

    statuses, materials = await in_rolled_back_migration(check)

    # statuses.started_at is NOT NULL, so such a material cannot be carried over
    assert statuses == []
    assert materials == [(None, None)]


def _completed_at_index(conn: Connection) -> list[dict]:
    return [
        index
        for index in sa.inspect(conn).get_indexes("materials")
        if index["name"] == REVISION_0006.INDEX_NAME
    ]


async def test_0006_downgrade_drops_and_upgrade_restores_the_partial_index():
    def check(conn: Connection) -> tuple[list[dict], list[dict], str]:
        revisions.downgrade_to(REVISION_0005)
        dropped = _completed_at_index(conn)
        REVISION_0006.upgrade()
        definition = conn.scalar(
            sa.text("SELECT indexdef FROM pg_indexes WHERE indexname = :name"),
            {"name": REVISION_0006.INDEX_NAME},
        )
        return dropped, _completed_at_index(conn), definition

    dropped, restored, definition = await in_rolled_back_migration(check)

    assert dropped == []
    assert [index["column_names"] for index in restored] == [["completed_at"]]
    assert definition.endswith("WHERE (completed_at IS NOT NULL)")


def _next_index(conn: Connection) -> int:
    return conn.execute(sa.text("SELECT nextval('materials_index_seq')")).scalar_one()


async def test_0007_downgrade_numbers_materials_by_sort_key_and_upgrade_drops_the_column():
    def check(conn: Connection) -> tuple:
        ids = [
            _insert_material(conn, added_at=ADDED_AT + datetime.timedelta(days=offset))
            for offset in (2, 0, 1)
        ]
        REVISION_0007.downgrade()
        indexes = dict(_rows(conn, sa.text('SELECT material_id, "index" FROM materials')))
        constraints = {
            constraint["name"]
            for constraint in sa.inspect(conn).get_unique_constraints("materials")
        }
        [index_column] = [
            column
            for column in sa.inspect(conn).get_columns("materials")
            if column["name"] == REVISION_0007.COLUMN_NAME
        ]
        next_index = _next_index(conn)
        REVISION_0007.upgrade()
        sequences = conn.scalar(
            sa.text(
                "SELECT count(*) FROM pg_class "
                "WHERE relkind = 'S' AND relname = 'materials_index_seq'",
            ),
        )
        return (
            [indexes[material_id] for material_id in ids],
            constraints,
            index_column["nullable"],
            next_index,
            _columns(conn, "materials"),
            sequences,
        )

    (
        indexes,
        constraints,
        nullable,
        next_index,
        columns,
        sequences,
    ) = await in_rolled_back_migration(check)

    assert indexes == [3, 1, 2]
    assert REVISION_0007.CONSTRAINT_NAME in constraints
    assert nullable is False
    assert next_index == 4
    assert REVISION_0007.COLUMN_NAME not in columns
    assert sequences == 0


async def test_0007_downgrade_on_an_empty_table_starts_the_sequence_at_one():
    def check(conn: Connection) -> int:
        REVISION_0007.downgrade()
        return _next_index(conn)

    assert await in_rolled_back_migration(check) == 1


def _index_definitions(conn: Connection) -> dict[str, str]:
    rows = conn.execute(
        sa.text(
            "SELECT indexname, indexdef FROM pg_indexes "
            "WHERE tablename IN ('materials', 'reading_log', 'notes') "
            "AND indexname LIKE 'ix\\_%'",
        ),
    )
    return {name: definition.split(" USING btree ", 1)[1] for name, definition in rows}


LISTING_INDEXES_AT_0008 = {
    REVISION_0008.READING_LOG_INDEX_NAME: "(date, sort_key)",
    REVISION_0008.COMPLETED_INDEX_NAME: (
        "(completed_at, sort_key) WHERE (completed_at IS NOT NULL)"
    ),
    REVISION_0008.STARTED_INDEX_NAME: "(started_at, sort_key) WHERE (started_at IS NOT NULL)",
    REVISION_0008.LINKS_INDEX_NAME: "(link_id, note_number, sort_key)",
}


async def test_0008_replaces_the_completed_at_index_by_the_listing_indexes():
    def check(conn: Connection) -> tuple[dict[str, str], dict[str, str]]:
        revisions.downgrade_to(REVISION_0007)
        at_0007 = _index_definitions(conn)
        REVISION_0008.upgrade()
        return at_0007, _index_definitions(conn)

    at_0007, at_0008 = await in_rolled_back_migration(check)

    assert REVISION_0008.COMPLETED_AT_INDEX_NAME in at_0007
    assert not set(LISTING_INDEXES_AT_0008) & set(at_0007)
    assert REVISION_0008.COMPLETED_AT_INDEX_NAME not in at_0008
    assert {name: at_0008[name] for name in LISTING_INDEXES_AT_0008} == LISTING_INDEXES_AT_0008
    assert set(at_0008) - set(LISTING_INDEXES_AT_0008) == set(at_0007) - {
        REVISION_0008.COMPLETED_AT_INDEX_NAME,
    }
