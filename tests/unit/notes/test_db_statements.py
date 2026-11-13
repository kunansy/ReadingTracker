import itertools
from contextlib import asynccontextmanager
from uuid import UUID

import pytest
from sqlalchemy.dialects import postgresql

from tests.unit.notes.conftest import FakeSession, build_note, note_id
from tracker.common import database
from tracker.notes import db


NOTE_ID = UUID(int=1)
MATERIAL_ID = UUID(int=2)
LINK_ID = UUID(int=3)

BASE_WHERE = "WHERE NOT n.is_deleted"
ORDER_BY = "ORDER BY n.note_number"
LINKS_COUNT = (
    "(select count(1) as links_count from notes "
    "where link_id = n.note_id and not is_deleted)"
)


def _compile(stmt):
    return stmt.compile(dialect=postgresql.dialect())


def _where(stmt) -> str:
    sql = str(_compile(stmt))
    return sql[sql.index("WHERE") : sql.index(" ORDER BY")]


@pytest.fixture
def fake_session(mocker):
    def install(rows: list) -> FakeSession:
        session = FakeSession(rows)

        @asynccontextmanager
        async def open_session(**_kwargs):
            yield session

        mocker.patch.object(database, "session", open_session)
        return session

    return install


class TestGetNoteStmt:
    def test_without_filters_selects_not_deleted_notes_ordered_by_number(self):
        compiled = _compile(db._get_note_stmt())
        sql = str(compiled)

        assert LINKS_COUNT in sql
        assert "FROM notes AS n" in sql
        assert sql.endswith(f"{BASE_WHERE} {ORDER_BY}")
        assert compiled.params == {}

    @pytest.mark.parametrize(
        ("with_note", "with_material", "with_link"),
        list(itertools.product([False, True], repeat=3)),
    )
    def test_every_filter_combination(self, with_note, with_material, with_link):
        stmt = db._get_note_stmt(
            note_id=NOTE_ID if with_note else None,
            material_id=MATERIAL_ID if with_material else None,
            link_id=LINK_ID if with_link else None,
        )

        expected_where = BASE_WHERE
        expected_params = {}
        if with_note:
            expected_where += " AND n.note_id = %(note_id_1)s::UUID"
            expected_params["note_id_1"] = str(NOTE_ID)
        if with_material:
            expected_where += " AND n.material_id = %(material_id_1)s::UUID"
            expected_params["material_id_1"] = str(MATERIAL_ID)
        if with_link:
            expected_where += " AND n.link_id = %(link_id_1)s::UUID"
            expected_params["link_id_1"] = str(LINK_ID)

        assert _where(stmt) == expected_where
        assert _compile(stmt).params == expected_params

    def test_string_ids_are_accepted(self):
        stmt = db._get_note_stmt(
            note_id=str(NOTE_ID),
            material_id=str(MATERIAL_ID),
            link_id=str(LINK_ID),
        )

        assert _compile(stmt).params == {
            "note_id_1": str(NOTE_ID),
            "material_id_1": str(MATERIAL_ID),
            "link_id_1": str(LINK_ID),
        }

    def test_empty_string_ids_apply_no_filter(self):
        stmt = db._get_note_stmt(note_id="", material_id="", link_id="")

        assert _where(stmt) == BASE_WHERE


class TestSearchNotesStmt:
    def test_no_filters(self):
        stmt = db._search_notes_stmt(material_id=None, tags=set(), note_ids=None)

        assert _where(stmt) == BASE_WHERE
        assert _compile(stmt).params == {}

    def test_material_filter(self):
        stmt = db._search_notes_stmt(material_id=MATERIAL_ID, tags=set(), note_ids=None)

        assert _where(stmt) == f"{BASE_WHERE} AND n.material_id = %(material_id_1)s::UUID"
        assert _compile(stmt).params == {"material_id_1": str(MATERIAL_ID)}

    def test_tags_filter_uses_sorted_tags(self):
        stmt = db._search_notes_stmt(material_id=None, tags={"b", "a", "c"}, note_ids=None)

        assert _where(stmt) == f"{BASE_WHERE} AND n.tags @> %(tags_1)s::JSONB"
        assert _compile(stmt).params == {"tags_1": ["a", "b", "c"]}

    def test_note_ids_filter_uses_string_ids(self):
        stmt = db._search_notes_stmt(
            material_id=None,
            tags=set(),
            note_ids=[note_id(1), note_id(2)],
        )

        assert _where(stmt) == f"{BASE_WHERE} AND n.note_id IN (__[POSTCOMPILE_note_id_1])"
        assert _compile(stmt).params == {"note_id_1": [str(note_id(1)), str(note_id(2))]}

    def test_empty_note_ids_still_filter(self):
        stmt = db._search_notes_stmt(material_id=None, tags=set(), note_ids=[])

        assert _where(stmt) == f"{BASE_WHERE} AND n.note_id IN (__[POSTCOMPILE_note_id_1])"
        assert _compile(stmt).params == {"note_id_1": []}

    def test_all_filters_together(self):
        stmt = db._search_notes_stmt(
            material_id=str(MATERIAL_ID),
            tags={"tag"},
            note_ids=(note_id(7),),
        )

        assert _where(stmt) == (
            f"{BASE_WHERE} AND n.material_id = %(material_id_1)s::UUID "
            "AND n.tags @> %(tags_1)s::JSONB "
            "AND n.note_id IN (__[POSTCOMPILE_note_id_1])"
        )
        assert _compile(stmt).params == {
            "material_id_1": str(MATERIAL_ID),
            "tags_1": ["tag"],
            "note_id_1": [str(note_id(7))],
        }


class TestGetPossibleLinks:
    async def test_links_are_ordered_by_tag_overlap_keeping_ties_in_row_order(
        self,
        fake_session,
    ):
        rows = [
            build_note(1, tags={"a"}),
            build_note(2, tags={"a", "b", "c", "x"}),
            build_note(3, tags={"a", "b"}),
            build_note(4, tags={"b"}),
            build_note(5, tags={"z"}),
        ]
        fake_session(rows)

        links = await db.get_possible_links(note_id(99), {"a", "b", "c"})

        assert [link.note_number for link in links] == [2, 3, 1, 4, 5]

    async def test_no_rows_give_no_links(self, fake_session):
        fake_session([])

        assert await db.get_possible_links(note_id(99), {"a"}) == []

    async def test_empty_note_tags_keep_row_order(self, fake_session):
        fake_session([build_note(1, tags={"a"}), build_note(2, tags={"a", "b"})])

        links = await db.get_possible_links(note_id(99), set())

        assert [link.note_number for link in links] == [1, 2]

    async def test_statement_excludes_deleted_notes_and_the_note_itself(
        self,
        fake_session,
    ):
        session = fake_session([])

        await db.get_possible_links(note_id(99), {"a"})

        [stmt] = session.statements
        compiled = _compile(stmt)
        assert "WHERE NOT notes.is_deleted AND notes.note_id != %(note_id_1)s::UUID" in str(
            compiled,
        )
        assert compiled.params == {"note_id_1": note_id(99)}

    async def test_note_id_is_interpolated_into_sql_text_current_behaviour(
        self,
        fake_session,
    ):
        session = fake_session([])

        await db.get_possible_links(note_id(99), {"a"})

        assert (
            "tags ?| array(SELECT jsonb_array_elements_text(tags) FROM notes "
            f"WHERE note_id = '{note_id(99)}')"
        ) in str(_compile(session.statements[0]))


class TestGetSortedTags:
    @pytest.fixture
    def tag_sources(self, mocker):
        def install(*, tags: set[str], material_tags: list[str]):
            all_tags = mocker.patch.object(
                db,
                "_get_tags",
                mocker.AsyncMock(return_value=tags),
            )
            for_material = mocker.patch.object(
                db,
                "_get_material_tags",
                mocker.AsyncMock(return_value=material_tags),
            )
            return all_tags, for_material

        return install

    @pytest.mark.parametrize("material_id", [None, ""], ids=["none", "empty-string"])
    async def test_without_material_all_tags_are_sorted(self, tag_sources, material_id):
        _, for_material = tag_sources(tags={"b", "c", "a"}, material_tags=["z"])

        result = await db.get_sorted_tags(material_id=material_id)

        assert result == ["a", "b", "c"]
        for_material.assert_not_awaited()

    async def test_without_material_and_tags_is_empty(self, tag_sources):
        tag_sources(tags=set(), material_tags=[])

        assert await db.get_sorted_tags(material_id=None) == []

    async def test_material_tags_come_first_in_their_own_order(self, tag_sources):
        all_tags, for_material = tag_sources(
            tags={"a", "b", "c", "d"},
            material_tags=["d", "b"],
        )

        result = await db.get_sorted_tags(material_id=MATERIAL_ID)

        assert result == ["d", "b", "a", "c"]
        all_tags.assert_awaited_once_with()
        for_material.assert_awaited_once_with(MATERIAL_ID)

    @pytest.mark.parametrize(
        ("tags", "material_tags", "expected"),
        [
            ({"a", "b"}, [], ["a", "b"]),
            ({"a", "b"}, ["b", "a"], ["b", "a"]),
            (set(), [], []),
            ({"a"}, ["only_material"], ["only_material", "a"]),
        ],
        ids=[
            "material-without-tags",
            "material-has-every-tag",
            "no-tags-at-all",
            "material-tag-missing-from-all-tags",
        ],
    )
    async def test_set_arithmetic(self, tag_sources, tags, material_tags, expected):
        tag_sources(tags=tags, material_tags=material_tags)

        assert await db.get_sorted_tags(material_id=str(MATERIAL_ID)) == expected
