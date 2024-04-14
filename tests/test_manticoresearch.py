import random
import uuid
from uuid import UUID

import pytest

from tracker.common import manticoresearch
from tracker.common.manticoresearch import SearchResult
from tracker.notes import db as notes_db


def test_get_search_query():
    assert manticoresearch._get_search_query() == """
    SELECT
        note_id,
        HIGHLIGHT({snippet_separator='',before_match='',after_match=''}),
        HIGHLIGHT({snippet_separator='',before_match='**',after_match='**'})
    FROM notes
    WHERE match(%s)
    ORDER BY weight() DESC
    """


@pytest.mark.asyncio
async def test_readiness():
    assert await manticoresearch.readiness() is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query, expected", (
        ("", {}),
        ("иллюзия", {
            UUID("18c04e3d-f692-4328-8569-9e048ef73e41"): SearchResult(
                replace_substring="При чтении книги опасна «иллюзия понимания», когда кажется, что понял, а на самом деле не понял или понял не правильно.",
                snippet="При чтении книги опасна «**иллюзия** понимания», когда кажется, что понял, а на самом деле не понял или понял не правильно."),
            UUID("1ededb71-8d1c-6dd0-a189-d1de5f641398"): SearchResult(
                replace_substring=" вызывать `module::func()`, не создавая иллюзии определённости функции в локальном crate.",
                snippet=" вызывать `module::func()`, не создавая **иллюзии** определённости функции в локальном crate."),
        }),
        ("занести", {
             UUID("018e9dbe-1d3d-7a5a-b437-9bfa65171b42"): SearchResult(
                 replace_substring="`fld st0` — занести в регистровый стек число из другого регистра или памяти.",
                 snippet="`fld st0` — **занести** в регистровый стек число из другого регистра или памяти."),
             UUID("1c2fc59d-5313-4615-9290-e8668abe2fc0"): SearchResult(
                 replace_substring="`pushfd` — занести в стек значение регистра флагов.\r\n`popfd` — извлечь из стека значения в регистр флагов.",
                 snippet="`pushfd` — **занести** в стек значение регистра флагов.\r\n`popfd` — извлечь из стека значения в регистр флагов."),
             UUID("688d59d1-6932-4795-a353-08463ea10c9c"): SearchResult(
                 replace_substring="Команда `lea` вычислит адрес второго операнда и занесёт в первый (*только регистровый*):\r\n`lea eax, [1000+ebx+8*ecx]`.",
                 snippet="Команда `lea` вычислит адрес второго операнда и **занесёт** в первый (*только регистровый*):\r\n`lea eax, [1000+ebx+8*ecx]`."),
        }),
    )
)
async def test_search(query, expected):
    assert await manticoresearch.search(query) == expected


@pytest.mark.asyncio
async def test_cursor():
    query = "select 1 + 1"
    async with manticoresearch._cursor() as cur:
        await cur.execute(query)
        result, = await cur.fetchone()

    assert result == 2


@pytest.mark.asyncio
async def test_cursor_error():
    query = "select * from not_exist"
    with pytest.raises(manticoresearch.ManticoreException) as e:
        async with manticoresearch._cursor() as cur:
            await cur.execute(query)

    assert str(e.value) == '(1064, "unknown local table(s) \'not_exist\' in search request")'


@pytest.mark.asyncio
async def test_get_notes():
    notes: list[manticoresearch.Note] = await manticoresearch._get_notes()
    notes_all: list[notes_db.Note] = await notes_db.get_notes()

    a_note: manticoresearch.Note = random.choice(notes)
    right_note = [note for note in notes_all if note.note_id == a_note.note_id][0]

    assert len(notes) == len(notes_all)
    assert a_note.note_id == right_note.note_id
    assert a_note.content == right_note.content
    assert a_note.added_at == right_note.added_at


@pytest.mark.asyncio
async def test_get_note():
    notes_all: list[notes_db.Note] = await notes_db.get_notes()

    a_note: notes_db.Note = random.choice(notes_all)
    note = await manticoresearch._get_note(note_id=a_note.note_id)

    assert a_note.note_id == note.note_id
    assert a_note.content == note.content
    assert a_note.added_at == note.added_at


@pytest.mark.asyncio
async def test_get_note_not_found():
    with pytest.raises(ValueError) as e:
        await manticoresearch._get_note(note_id=uuid.uuid4())

    assert "Note" in str(e.value)
    assert "not found" in str(e.value)


@pytest.mark.asyncio
async def test_create_table():
    await manticoresearch._create_table()
