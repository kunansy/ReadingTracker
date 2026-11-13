import datetime
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy.dialects import postgresql

from tracker.common import manticoresearch
from tracker.common.manticoresearch import Note, SearchResult


NOTE_ID = UUID("018e9dbe-1d3d-7a5a-b437-9bfa65171b42")
OTHER_ID = UUID("1c2fc59d-5313-4615-9290-e8668abe2fc0")
ADDED_AT = datetime.datetime(2024, 1, 2, 3, 4, 5, 6)
# 2024-01-02 03:04:05 UTC, the fraction of a second is dropped
ADDED_AT_UNIX = 1_704_164_645


class _FakeConnection:
    def __init__(self, mocker) -> None:
        self.events: list[str] = []
        self.cur = mocker.Mock()
        self.cur.execute = mocker.AsyncMock()
        self.cur.executemany = mocker.AsyncMock()
        self.cur.fetchall = mocker.AsyncMock(return_value=[])
        self.cur.fetchone = mocker.AsyncMock(return_value=None)
        self.cursor_exit_error: Exception | None = None
        self.commit_error: Exception | None = None

    @asynccontextmanager
    async def _cursor(self):
        self.events.append("cursor")
        yield self.cur
        self.events.append("cursor closed")
        if self.cursor_exit_error:
            raise self.cursor_exit_error

    def cursor(self):
        return self._cursor()

    async def commit(self) -> None:
        self.events.append("commit")
        if self.commit_error:
            raise self.commit_error

    async def rollback(self) -> None:
        self.events.append("rollback")

    def close(self) -> None:
        self.events.append("close")


@pytest.fixture
def conn(mocker) -> _FakeConnection:
    conn = _FakeConnection(mocker)
    conn.connect = mocker.patch.object(
        manticoresearch.aiomysql,
        "connect",
        mocker.AsyncMock(return_value=conn),
    )
    return conn


@pytest.fixture
def database_session(mocker):
    def _install(rows: list[SimpleNamespace]) -> list:
        executed = []

        async def _execute(stmt):
            executed.append(stmt)
            return SimpleNamespace(
                all=lambda: rows,
                one_or_none=lambda: rows[0] if rows else None,
            )

        @asynccontextmanager
        async def _session(**_kwargs):
            yield SimpleNamespace(execute=_execute)

        mocker.patch("tracker.common.database.session", _session)
        return executed

    return _install


def _compile(stmt) -> str:
    compiled = stmt.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True},
    )
    return " ".join(str(compiled).split())


def _row(note_id: UUID = NOTE_ID, content: str = "content") -> SimpleNamespace:
    return SimpleNamespace(note_id=note_id, content=content, added_at=ADDED_AT)


async def test_cursor_connects_with_settings_commits_and_closes(conn):
    async with manticoresearch._cursor() as cur:
        assert cur is conn.cur
        assert conn.events == ["cursor"]

    conn.connect.assert_awaited_once_with(host="127.0.0.1", port=1, db="Manticore")
    assert conn.events == ["cursor", "cursor closed", "commit", "close"]


async def test_cursor_rolls_back_and_wraps_error_of_the_block(conn):
    error = RuntimeError("unknown local table")

    with pytest.raises(manticoresearch.ManticoreException) as exc_info:
        async with manticoresearch._cursor():
            raise error

    assert exc_info.value.args == (error,)
    assert exc_info.value.__cause__ is error
    assert conn.events == ["cursor", "rollback", "close"]


async def test_cursor_rolls_back_when_commit_fails(conn):
    conn.commit_error = OSError("connection lost")

    with pytest.raises(manticoresearch.ManticoreException) as exc_info:
        async with manticoresearch._cursor():
            pass

    assert exc_info.value.__cause__ is conn.commit_error
    assert conn.events == ["cursor", "cursor closed", "commit", "rollback", "close"]


async def test_cursor_rolls_back_when_cursor_cannot_be_closed(conn):
    conn.cursor_exit_error = OSError("broken pipe")

    with pytest.raises(manticoresearch.ManticoreException):
        async with manticoresearch._cursor():
            pass

    assert conn.events == ["cursor", "cursor closed", "rollback", "close"]


async def test_cursor_propagates_connection_failure_unwrapped(mocker):
    mocker.patch.object(
        manticoresearch.aiomysql,
        "connect",
        mocker.AsyncMock(side_effect=OSError("refused")),
    )

    with pytest.raises(OSError, match="refused"):
        async with manticoresearch._cursor():
            pass


def test_get_note_stmt_skips_deleted_notes():
    assert _compile(manticoresearch._get_note_stmt()) == (
        "SELECT notes.note_id, notes.content, notes.added_at "
        "FROM notes WHERE NOT notes.is_deleted"
    )


async def test_get_notes_maps_rows(database_session):
    executed = database_session([_row(), _row(OTHER_ID, "Заметка")])

    notes = await manticoresearch._get_notes()

    assert notes == [
        Note(note_id=NOTE_ID, content="content", added_at=ADDED_AT),
        Note(note_id=OTHER_ID, content="Заметка", added_at=ADDED_AT),
    ]
    assert [_compile(stmt) for stmt in executed] == [
        "SELECT notes.note_id, notes.content, notes.added_at "
        "FROM notes WHERE NOT notes.is_deleted",
    ]


async def test_get_notes_of_empty_table(database_session):
    database_session([])

    assert await manticoresearch._get_notes() == []


async def test_get_note_returns_found_note(database_session):
    executed = database_session([_row()])

    note = await manticoresearch._get_note(note_id=NOTE_ID)

    assert note == Note(note_id=NOTE_ID, content="content", added_at=ADDED_AT)
    assert [_compile(stmt) for stmt in executed] == [
        "SELECT notes.note_id, notes.content, notes.added_at "
        "FROM notes WHERE NOT notes.is_deleted "
        "AND notes.note_id = '018e9dbe-1d3d-7a5a-b437-9bfa65171b42'",
    ]


async def test_get_note_raises_value_error_when_missing(database_session):
    database_session([])

    with pytest.raises(ValueError) as exc_info:
        await manticoresearch._get_note(note_id=NOTE_ID)

    assert str(exc_info.value) == "Note 018e9dbe-1d3d-7a5a-b437-9bfa65171b42 not found"


async def test_drop_table_executes_drop(conn):
    await manticoresearch._drop_table()

    conn.cur.execute.assert_awaited_once_with("DROP TABLE IF EXISTS notes")
    assert conn.events[-2:] == ["commit", "close"]


async def test_create_table_executes_create_with_morphology(conn):
    await manticoresearch._create_table()

    conn.cur.execute.assert_awaited_once_with(manticoresearch.CREATE_TABLE_QUERY)
    assert " ".join(manticoresearch.CREATE_TABLE_QUERY.split()) == (
        "CREATE TABLE IF NOT EXISTS notes ( note_id string, content text, "
        "added_at timestamp) morphology='lemmatize_ru_all, lemmatize_en_all'"
    )


async def test_insert_all_without_notes_does_not_connect(conn):
    await manticoresearch._insert_all()

    conn.connect.assert_not_awaited()
    conn.cur.executemany.assert_not_awaited()


async def test_insert_all_inserts_every_note_in_one_batch(conn):
    notes = [
        Note(note_id=NOTE_ID, content="first", added_at=ADDED_AT),
        Note(note_id=OTHER_ID, content="Вторая", added_at=ADDED_AT),
    ]

    await manticoresearch._insert_all(*notes)

    assert conn.cur.executemany.await_count == 1
    query, rows = conn.cur.executemany.await_args.args
    assert query == "INSERT INTO notes (note_id, content, added_at) VALUES (%s,%s,%s)"
    assert list(rows) == [
        (NOTE_ID, "first", ADDED_AT_UNIX),
        (OTHER_ID, "Вторая", ADDED_AT_UNIX),
    ]
    assert conn.events[-2:] == ["commit", "close"]


async def test_init_recreates_table_then_inserts_all_notes(mocker):
    notes = [Note(note_id=NOTE_ID, content="first", added_at=ADDED_AT)]
    manager = mocker.Mock()
    for name, return_value in (
        ("_drop_table", None),
        ("_create_table", None),
        ("_get_notes", notes),
        ("_insert_all", None),
    ):
        mock = mocker.AsyncMock(return_value=return_value)
        mocker.patch.object(manticoresearch, name, mock)
        manager.attach_mock(mock, name)

    await manticoresearch.init()

    assert manager.mock_calls == [
        mocker.call._drop_table(),
        mocker.call._create_table(),
        mocker.call._get_notes(),
        mocker.call._insert_all(*notes),
    ]


async def test_init_stops_when_table_cannot_be_created(mocker):
    mocker.patch.object(manticoresearch, "_drop_table", mocker.AsyncMock())
    mocker.patch.object(
        manticoresearch,
        "_create_table",
        mocker.AsyncMock(side_effect=manticoresearch.ManticoreException("down")),
    )
    get_notes = mocker.patch.object(manticoresearch, "_get_notes", mocker.AsyncMock())

    with pytest.raises(manticoresearch.ManticoreException):
        await manticoresearch.init()

    get_notes.assert_not_awaited()


@pytest.mark.parametrize("note_id", [NOTE_ID, str(NOTE_ID)], ids=["uuid", "string"])
async def test_delete_removes_note_by_id(conn, note_id):
    await manticoresearch.delete(note_id)

    conn.cur.execute.assert_awaited_once_with(
        "DELETE FROM notes WHERE note_id=%s",
        note_id,
    )
    assert conn.events[-2:] == ["commit", "close"]


async def test_insert_note_inserts_one_row(conn):
    await manticoresearch.insert_note(
        note_id=NOTE_ID, content="content", added_at=ADDED_AT
    )

    query, rows = conn.cur.executemany.await_args.args
    assert query == manticoresearch.INSERT_QUERY
    assert list(rows) == [(NOTE_ID, "content", ADDED_AT_UNIX)]


async def test_insert_note_strips_content_current_behaviour(conn):
    await manticoresearch.insert_note(
        note_id=NOTE_ID,
        content="  padded \n",
        added_at=ADDED_AT,
    )

    _, rows = conn.cur.executemany.await_args.args
    assert list(rows) == [(NOTE_ID, "padded", ADDED_AT_UNIX)]


async def test_update_content_deletes_then_inserts_in_one_transaction(conn, mocker):
    await manticoresearch.update_content(
        note_id=NOTE_ID,
        content="Новый текст",
        added_at=ADDED_AT,
    )

    assert conn.cur.execute.await_args_list == [
        mocker.call("DELETE FROM notes WHERE note_id=%s", NOTE_ID),
        mocker.call(
            "INSERT INTO notes (note_id, content, added_at) VALUES (%s,%s,%s)",
            (NOTE_ID, "Новый текст", ADDED_AT_UNIX),
        ),
    ]
    assert conn.events.count("commit") == 1
    assert conn.connect.await_count == 1


async def test_update_content_rolls_back_when_insert_fails(conn):
    conn.cur.execute.side_effect = [None, RuntimeError("insert failed")]

    with pytest.raises(manticoresearch.ManticoreException):
        await manticoresearch.update_content(
            note_id=NOTE_ID,
            content="content",
            added_at=ADDED_AT,
        )

    assert conn.events == ["cursor", "rollback", "close"]


def test_get_search_query():
    assert (
        manticoresearch._get_search_query()
        == """
    SELECT
        note_id,
        HIGHLIGHT({snippet_separator='',before_match='',after_match=''}),
        HIGHLIGHT({snippet_separator='',before_match='**',after_match='**'})
    FROM notes
    WHERE match(%s)
    ORDER BY weight() DESC
    """
    )


async def test_search_with_empty_query_does_not_connect(conn):
    assert await manticoresearch.search("") == {}

    conn.connect.assert_not_awaited()


async def test_search_maps_rows_by_note_id(conn):
    conn.cur.fetchall.return_value = [
        (str(NOTE_ID), "опасна иллюзия понимания", "опасна **иллюзия** понимания"),
        (str(OTHER_ID), "an illusion", "an **illusion**"),
    ]

    result = await manticoresearch.search("иллюзия")

    assert result == {
        NOTE_ID: SearchResult(
            replace_substring="опасна иллюзия понимания",
            snippet="опасна **иллюзия** понимания",
        ),
        OTHER_ID: SearchResult(
            replace_substring="an illusion", snippet="an **illusion**"
        ),
    }
    conn.cur.execute.assert_awaited_once_with(
        manticoresearch._get_search_query(),
        "иллюзия",
    )


async def test_search_sends_user_query_as_parameter(conn):
    query = "x') OR 1=1 --"

    await manticoresearch.search(query)

    sql, argument = conn.cur.execute.await_args.args
    assert query not in sql
    assert argument == query


async def test_search_without_matches(conn):
    conn.cur.fetchall.return_value = []

    assert await manticoresearch.search("nothing") == {}


async def test_search_keeps_last_of_duplicated_note_ids(conn):
    conn.cur.fetchall.return_value = [
        (str(NOTE_ID), "first", "**first**"),
        (str(NOTE_ID), "second", "**second**"),
    ]

    result = await manticoresearch.search("query")

    assert result == {
        NOTE_ID: SearchResult(replace_substring="second", snippet="**second**"),
    }


async def test_search_wraps_invalid_note_id_of_the_index(conn):
    conn.cur.fetchall.return_value = [("not-a-uuid", "a", "b")]

    with pytest.raises(manticoresearch.ManticoreException):
        await manticoresearch.search("query")

    assert conn.events[-2:] == ["rollback", "close"]


async def test_autocompletion_returns_first_column_of_rows(conn):
    conn.cur.fetchall.return_value = [("**при**вет",), ("**при**мер",)]

    result = await manticoresearch.autocompletion(query="при")

    assert result == ["**при**вет", "**при**мер"]


async def test_autocompletion_without_matches(conn):
    assert await manticoresearch.autocompletion(query="zzz") == []


async def test_autocompletion_builds_prefix_match_with_default_limit(conn):
    await manticoresearch.autocompletion(query="при")

    sql, (match, limit) = conn.cur.execute.await_args.args
    assert " ".join(sql.split()) == (
        "SELECT HIGHLIGHT({snippet_separator='',before_match='**',after_match='**'}) "
        "FROM notes WHERE MATCH(%s) ORDER BY WEIGHT() DESC LIMIT %s"
    )
    assert match == "@content при*"
    assert limit == 5


@pytest.mark.parametrize(
    "limit", [1, 0, -1, 10**9], ids=["one", "zero", "negative", "huge"]
)
async def test_autocompletion_passes_limit_unchecked_current_behaviour(conn, limit):
    await manticoresearch.autocompletion(query="a", limit=limit)

    _, (_, argument) = conn.cur.execute.await_args.args
    assert argument == limit


async def test_autocompletion_sends_user_query_as_parameter(conn):
    query = "x') OR 1=1; DROP TABLE notes; --"

    await manticoresearch.autocompletion(query=query)

    sql, *_ = conn.cur.execute.await_args.args
    assert query not in sql


@pytest.mark.parametrize(
    ("query", "match"),
    [
        ("dog's", "@content dog\\'s*"),
        ("a-b (c)", "@content a\\-b \\(c\\)*"),
        ('!"$/<@^|~', '@content \\!\\"\\$\\/\\<\\@\\^\\|\\~*'),
        ("back\\slash", "@content back\\\\slash*"),
        ("при", "@content при*"),
    ],
    ids=["quote", "operators", "every-other-special", "backslash", "plain"],
)
async def test_autocompletion_escapes_the_query_syntax(conn, query, match):
    await manticoresearch.autocompletion(query=query)

    _, (sent, _) = conn.cur.execute.await_args.args
    assert sent == match


@pytest.mark.parametrize(
    ("added_at", "expected"),
    [
        (ADDED_AT, ADDED_AT_UNIX),
        (ADDED_AT.replace(tzinfo=datetime.UTC), ADDED_AT_UNIX),
        (
            datetime.datetime(
                2024, 1, 2, 6, 4, 5, tzinfo=datetime.timezone(datetime.timedelta(hours=3))
            ),
            ADDED_AT_UNIX,
        ),
    ],
    ids=["naive-is-utc", "utc", "other-zone"],
)
def test_to_unix_time(added_at, expected):
    assert manticoresearch._to_unix_time(added_at) == expected


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        (("uptime", "0"), False),
        (("uptime", "4"), False),
        (("uptime", "5"), True),
        (("uptime", "6"), True),
        (("uptime", "86400"), True),
        (("uptime", ""), False),
        (("uptime", "N/A"), False),
        (("uptime", "-5"), False),
        (("uptime", "5.5"), False),
    ],
    ids=[
        "zero",
        "below",
        "at-threshold",
        "above",
        "day",
        "empty",
        "text",
        "negative",
        "float",
    ],
)
async def test_readiness_depends_on_uptime(conn, row, expected):
    conn.cur.fetchone.return_value = row

    assert await manticoresearch.readiness() is expected

    conn.cur.execute.assert_awaited_once_with("SHOW STATUS like 'uptime'")


async def test_readiness_is_false_when_status_is_missing(conn):
    conn.cur.fetchone.return_value = None

    assert await manticoresearch.readiness() is False


async def test_readiness_is_false_when_query_fails(conn):
    conn.cur.execute.side_effect = OSError("connection lost")

    assert await manticoresearch.readiness() is False


async def test_readiness_is_false_when_manticore_is_unreachable(mocker):
    mocker.patch.object(
        manticoresearch.aiomysql,
        "connect",
        mocker.AsyncMock(side_effect=OSError("refused")),
    )

    assert await manticoresearch.readiness() is False
