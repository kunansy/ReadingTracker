from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from tests.unit.helpers import compile_sql, make_material, midnight, uid
from tests.unit.materials.helpers import fake_session_factory
from tracker.common import database
from tracker.materials import db
from tracker.models import enums


MATERIAL_COLUMNS = (
    "SELECT materials.material_id, materials.title, materials.authors, materials.pages, "
    "materials.material_type, materials.tags, materials.link, materials.added_at, "
    "materials.is_outlined, materials.started_at, materials.completed_at, materials.sort_key"
)
LAST_LOG_DATE = (
    "(SELECT max(reading_log.date) AS max_1 FROM reading_log "
    "WHERE reading_log.material_id = materials.material_id)"
)
READING_MATERIALS = (
    f"{MATERIAL_COLUMNS}, "
    f"coalesce({LAST_LOG_DATE}, date(materials.started_at)) AS last_read_at "
    "FROM materials "
    "WHERE materials.started_at IS NOT NULL AND materials.completed_at IS NULL"
)


def test_free_materials_are_not_started_ordered_by_sort_key():
    sql = compile_sql(db._get_free_materials_stmt())

    assert sql == (
        f"{MATERIAL_COLUMNS} FROM materials "
        "WHERE materials.started_at IS NULL ORDER BY materials.sort_key"
    )


def test_reading_materials_are_ordered_by_the_last_log_date():
    sql = compile_sql(db._get_reading_materials_stmt())

    assert sql == f"{READING_MATERIALS} ORDER BY {LAST_LOG_DATE} DESC"


def test_completed_materials_without_filters():
    sql = compile_sql(db._get_completed_materials_stmt())

    assert sql == (
        f"{MATERIAL_COLUMNS} FROM materials "
        "WHERE materials.completed_at IS NOT NULL ORDER BY materials.completed_at"
    )


@pytest.mark.parametrize(
    ("filters", "expected_where"),
    [
        ({"material_type": enums.MaterialTypesEnum.lecture}, "materials.material_type = 'lecture'"),
        ({"is_outlined": True}, "materials.is_outlined = true"),
        ({"is_outlined": False}, "materials.is_outlined = false"),
    ],
    ids=["type", "outlined", "not-outlined"],
)
def test_completed_materials_filters(filters, expected_where):
    sql = compile_sql(db._get_completed_materials_stmt(**filters))

    assert sql == (
        f"{MATERIAL_COLUMNS} FROM materials "
        f"WHERE materials.completed_at IS NOT NULL AND {expected_where} "
        "ORDER BY materials.completed_at"
    )


def _compile_params(stmt):
    compiled = stmt.compile(dialect=postgresql.dialect())
    return " ".join(str(compiled).split()), compiled.params


@pytest.mark.parametrize(
    ("tags", "expected"),
    [({"sql"}, ["sql"]), ({"b", "a", "c"}, ["a", "b", "c"])],
    ids=["one-tag", "sorted-tags"],
)
def test_completed_materials_filter_by_tags_with_jsonb_containment(tags, expected):
    sql, params = _compile_params(db._get_completed_materials_stmt(tags=tags))

    assert sql.endswith(
        "WHERE materials.completed_at IS NOT NULL "
        "AND materials.tags @> %(tags_1)s::JSONB ORDER BY materials.completed_at",
    )
    assert params == {"tags_1": expected}


def test_completed_materials_all_filters():
    sql, params = _compile_params(
        db._get_completed_materials_stmt(
            material_type=enums.MaterialTypesEnum.book,
            is_outlined=False,
            tags={"a"},
        ),
    )

    assert sql.endswith(
        "WHERE materials.completed_at IS NOT NULL "
        "AND materials.material_type = %(material_type_1)s "
        "AND materials.is_outlined = false "
        "AND materials.tags @> %(tags_1)s::JSONB ORDER BY materials.completed_at",
    )
    assert params == {"material_type_1": enums.MaterialTypesEnum.book, "tags_1": ["a"]}


@pytest.mark.parametrize(
    "filters",
    [
        {"material_type": None},
        {"is_outlined": None},
        {"tags": None},
        {"tags": set()},
    ],
    ids=["no-type", "no-outlined", "no-tags", "empty-tags"],
)
def test_completed_materials_empty_filter_is_not_applied(filters):
    assert compile_sql(db._get_completed_materials_stmt(**filters)) == compile_sql(
        db._get_completed_materials_stmt(),
    )


@pytest.mark.parametrize("is_outlined", [True, False], ids=["outlined-only", "all"])
def test_repeating_queue_statement(is_outlined, frozen_now):
    stmt, repeat_at = db._get_repeating_queue_stmt(is_outlined=is_outlined)

    sql = compile_sql(stmt)
    last_seen = "date(coalesce(repeats_stat.last_repeated_at, materials.completed_at))"
    where = (
        "WHERE materials.completed_at IS NOT NULL "
        "AND NOT (materials.is_outlined AND coalesce(notes_stat.notes_count, 0) = 0) "
        f"AND '{frozen_now.date().isoformat()}' - {last_seen} "
        ">= 30 * (coalesce(repeats_stat.repeats_count, 0) + 1)"
    )
    if is_outlined:
        where += " AND materials.is_outlined"
    assert sql.endswith(where)
    assert "FROM notes WHERE NOT notes.is_deleted GROUP BY notes.material_id" in sql
    assert "ORDER BY" not in sql
    assert compile_sql(repeat_at) == (
        f"{last_seen} + 30 * CAST(coalesce(repeats_stat.repeats_count, 0) AS INTEGER)"
    )


class _ExecutingSession:
    def __init__(self, mocker, first: object) -> None:
        result = mocker.Mock()
        result.first.return_value = first
        self.execute = mocker.AsyncMock(return_value=result)


@pytest.fixture
def executed(mocker):
    def _install(first: object) -> _ExecutingSession:
        session = _ExecutingSession(mocker, first)
        mocker.patch.object(database, "session", fake_session_factory(session))
        return session

    return _install


async def test_last_material_started_returns_the_first_row(executed):
    session = executed(SimpleNamespace(material_id=uid(4)))

    assert await db.get_last_material_started() == uid(4)
    assert compile_sql(session.execute.await_args.args[0]).endswith("LIMIT 1")


async def test_last_material_started_is_none_when_nothing_is_read(executed):
    executed(None)

    assert await db.get_last_material_started() is None


async def test_last_material_started_is_ordered_by_the_start_date(executed):
    session = executed(None)

    await db.get_last_material_started()

    sql = compile_sql(session.execute.await_args.args[0])
    assert sql == f"{READING_MATERIALS} ORDER BY materials.started_at DESC LIMIT 1"


@pytest.fixture
def tags_in_db(mocker):
    def _install(tags: list[str]):
        session = SimpleNamespace(scalars=mocker.AsyncMock(return_value=iter(tags)))
        mocker.patch.object(database, "session", fake_session_factory(session))
        return session

    return _install


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        ([], []),
        ([["python"]], ["python"]),
        ([["sql", "python"], ["go", "sql"], []], ["go", "python", "sql"]),
    ],
    ids=["no-materials", "single", "deduplicated-and-sorted"],
)
async def test_material_tags_are_flattened_deduplicated_and_sorted(tags_in_db, stored, expected):
    tags_in_db(stored)

    assert await db.get_material_tags() == expected


async def test_material_tags_query_skips_materials_without_tags(tags_in_db):
    session = tags_in_db([])

    await db.get_material_tags()

    sql, params = _compile_params(session.scalars.await_args.args[0])
    assert sql == "SELECT materials.tags FROM materials WHERE materials.tags != %(tags_1)s::JSONB"
    assert params == {"tags_1": []}


@pytest.fixture
def parse_response(mocker):
    return mocker.patch.object(
        db,
        "_parse_materials_response",
        mocker.AsyncMock(return_value=[make_material(started_at=midnight(-1))]),
    )


async def test_reading_materials_are_parsed_from_the_reading_statement(parse_response):
    materials = await db.get_reading_materials()

    assert materials == parse_response.return_value
    assert compile_sql(parse_response.await_args.kwargs["stmt"]) == compile_sql(
        db._get_reading_materials_stmt(),
    )


async def test_completed_materials_pass_filters_to_the_statement(parse_response):
    filters = {
        "material_type": enums.MaterialTypesEnum.article,
        "is_outlined": True,
        "tags": {"go"},
    }

    materials = await db._get_completed_materials(**filters)

    assert materials == parse_response.return_value
    assert _compile_params(parse_response.await_args.kwargs["stmt"]) == _compile_params(
        db._get_completed_materials_stmt(**filters),
    )


def test_to_material_ignores_extra_columns_and_keeps_strings_as_stored():
    row = make_material().model_dump() | {
        "title": "  Title  ",
        "sort_key": "key",
        "last_read_at": None,
    }

    material = db._to_material(row)

    assert material == make_material(title="  Title  ")
