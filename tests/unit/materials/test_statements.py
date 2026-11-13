from types import SimpleNamespace

import pytest

from tests.unit.materials.helpers import (
    compile_sql,
    fake_session_factory,
    make_material,
    midnight,
    uid,
)
from tracker.common import database
from tracker.materials import db
from tracker.models import enums


MATERIAL_COLUMNS = (
    "SELECT materials.material_id, materials.title, materials.authors, materials.pages, "
    "materials.material_type, materials.tags, materials.link, materials.added_at, "
    "materials.is_outlined, materials.started_at, materials.completed_at, materials.sort_key"
)
READING_MATERIALS = (
    "WITH reading_logs AS (SELECT reading_log.material_id AS material_id, "
    "max(reading_log.date) AS date FROM reading_log GROUP BY reading_log.material_id) "
    f"{MATERIAL_COLUMNS}, "
    "coalesce(reading_logs.date, date(materials.started_at)) AS last_read_at "
    "FROM materials LEFT OUTER JOIN reading_logs "
    "ON reading_logs.material_id = materials.material_id "
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

    assert sql == f"{READING_MATERIALS} ORDER BY reading_logs.date DESC"


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
        (
            {"tags": {"sql"}},
            "(string_to_array(materials.tags, ', ') @> CAST(ARRAY['sql'] AS TEXT[]))",
        ),
        (
            {"tags": {"sql", "python", "Ядро"}},
            "(string_to_array(materials.tags, ', ') "
            "@> CAST(ARRAY['python', 'sql', 'Ядро'] AS TEXT[]))",
        ),
        (
            {
                "material_type": enums.MaterialTypesEnum.book,
                "is_outlined": False,
                "tags": {"b", "a"},
            },
            "materials.material_type = 'book' AND materials.is_outlined = false "
            "AND (string_to_array(materials.tags, ', ') @> CAST(ARRAY['a', 'b'] AS TEXT[]))",
        ),
    ],
    ids=["type", "outlined", "not-outlined", "one-tag", "sorted-tags", "all-filters"],
)
def test_completed_materials_filters(filters, expected_where):
    sql = compile_sql(db._get_completed_materials_stmt(**filters))

    assert sql == (
        f"{MATERIAL_COLUMNS} FROM materials "
        f"WHERE materials.completed_at IS NOT NULL AND {expected_where} "
        "ORDER BY materials.completed_at"
    )


@pytest.mark.parametrize(
    "filters",
    [{"material_type": None}, {"is_outlined": None}, {"tags": None}, {"tags": set()}],
    ids=["no-type", "no-outlined", "no-tags", "empty-tags"],
)
def test_completed_materials_empty_filter_is_not_applied(filters):
    assert compile_sql(db._get_completed_materials_stmt(**filters)) == compile_sql(
        db._get_completed_materials_stmt(),
    )


def test_tag_filter_quotes_tag_literals():
    sql = compile_sql(db._get_completed_materials_stmt(tags={"o'reilly"}))

    assert "ARRAY['o''reilly']" in sql


@pytest.mark.parametrize("is_outlined", [True, False], ids=["outlined-only", "all"])
def test_repeating_queue_statement(is_outlined):
    stmt, repeat_at = db._get_repeating_queue_stmt(is_outlined=is_outlined)

    sql = compile_sql(stmt)
    last_seen = "date(coalesce(repeats_stat.last_repeated_at, materials.completed_at))"
    where = (
        "WHERE materials.completed_at IS NOT NULL "
        "AND NOT (materials.is_outlined AND coalesce(notes_stat.notes_count, 0) = 0) "
        f"AND date(now()) - {last_seen} >= 30 * (coalesce(repeats_stat.repeats_count, 0) + 1)"
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


@pytest.mark.xfail(
    strict=True,
    reason=(
        "BUG: tracker/materials/db.py:280-282 the second order_by() is appended to "
        "`ORDER BY reading_logs.date DESC`, so the material with the latest log wins "
        "over the last started one"
    ),
)
async def test_last_material_started_is_ordered_by_the_start_date(executed):
    session = executed(None)

    await db.get_last_material_started()

    sql = compile_sql(session.execute.await_args.args[0])
    assert sql == f"{READING_MATERIALS} ORDER BY materials.started_at DESC LIMIT 1"


async def test_last_material_started_order_current_behaviour(executed):
    session = executed(None)

    await db.get_last_material_started()

    sql = compile_sql(session.execute.await_args.args[0])
    assert sql == (
        f"{READING_MATERIALS} "
        "ORDER BY reading_logs.date DESC, materials.started_at DESC LIMIT 1"
    )


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
        ([], set()),
        (["python"], {"python"}),
        (["python, sql"], {"python", "sql"}),
        (["python,sql"], {"python", "sql"}),
        (["  Python ,SQL  ", "sql, Go"], {"python", "sql", "go"}),
        (["Ядро, ЯДРО , ядро"], {"ядро"}),
        (["data science, machine learning"], {"data science", "machine learning"}),
    ],
    ids=[
        "no-materials",
        "single",
        "comma-space",
        "comma-only",
        "strip-lower-dedupe",
        "cyrillic-case",
        "tag-with-space",
    ],
)
async def test_material_tags_are_split_stripped_and_lowercased(tags_in_db, stored, expected):
    tags_in_db(stored)

    assert await db.get_material_tags() == expected


@pytest.mark.parametrize("stored", ["", "python,", ", ,"], ids=["empty", "trailing", "blank"])
async def test_material_tags_keep_empty_tag_current_behaviour(tags_in_db, stored):
    tags_in_db([stored])

    assert "" in await db.get_material_tags()


async def test_material_tags_query_skips_materials_without_tags(tags_in_db):
    session = tags_in_db([])

    await db.get_material_tags()

    assert compile_sql(session.scalars.await_args.args[0]) == (
        "SELECT materials.tags FROM materials WHERE materials.tags IS NOT NULL"
    )


def test_listed_tag_cannot_be_found_by_the_filter_when_stored_without_space_current_behaviour():
    """`get_material_tags` lists 'sql' for a stored 'Python,SQL'; the filter looks for
    an element of string_to_array(tags, ', '), which is the whole 'Python,SQL' string.
    """
    sql = compile_sql(db._get_completed_materials_stmt(tags={"sql"}))

    assert "string_to_array(materials.tags, ', ') @> CAST(ARRAY['sql'] AS TEXT[])" in sql
    assert "lower(" not in sql


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
    assert compile_sql(parse_response.await_args.kwargs["stmt"]) == compile_sql(
        db._get_completed_materials_stmt(**filters),
    )


def test_to_material_ignores_extra_columns_and_strips_strings():
    row = make_material().model_dump() | {
        "title": "  Title  ",
        "sort_key": "key",
        "last_read_at": None,
    }

    material = db._to_material(row)

    assert material == make_material(title="Title")
