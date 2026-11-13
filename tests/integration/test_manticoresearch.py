import datetime
import uuid

import pytest

from tests.integration import factories
from tracker.common import manticoresearch, settings
from tracker.models import models
from tracker.notes import db as notes_db


ADDED_AT = datetime.datetime(2024, 1, 1, 10, 20, 30)  # noqa: DTZ001
RUSSIAN = "Собаки бегают по лесу."
ENGLISH = "Dogs are running in the forest."
READY_UPTIME_SECONDS = 5


async def _stored() -> dict[uuid.UUID, str]:
    async with manticoresearch._cursor() as cur:
        await cur.execute("SELECT note_id, content FROM notes LIMIT 1000")
        return {uuid.UUID(note_id): content for note_id, content in await cur.fetchall()}


async def _insert(content: str, note_id: uuid.UUID | None = None) -> uuid.UUID:
    note_id = note_id or uuid.uuid4()
    await manticoresearch.insert_note(note_id=note_id, content=content, added_at=ADDED_AT)
    return note_id


async def test_table_starts_empty(manticore):
    assert await _stored() == {}


async def test_insert_note_stores_the_content(manticore):
    note_id = await _insert(RUSSIAN)

    assert await _stored() == {note_id: RUSSIAN}


async def test_insert_note_stores_added_at(manticore):
    await _insert(RUSSIAN)

    async with manticoresearch._cursor() as cur:
        await cur.execute("SELECT added_at FROM notes")
        [[added_at]] = await cur.fetchall()

    assert added_at != 0


@pytest.mark.parametrize(
    ("content", "query", "snippet"),
    [
        (RUSSIAN, "собаки", "**Собаки** бегают по лесу."),
        (RUSSIAN, "собака", "**Собаки** бегают по лесу."),
        (RUSSIAN, "бегать лес", "Собаки **бегают** по **лесу**."),
        (ENGLISH, "dogs", "**Dogs** are running in the forest."),
        (ENGLISH, "dog", "**Dogs** are running in the forest."),
        (ENGLISH, "run forests", "Dogs are **running** in the **forest**."),
        (ENGLISH, "DOG", "**Dogs** are running in the forest."),
    ],
    ids=[
        "russian-exact",
        "russian-other-form",
        "russian-two-lemmas",
        "english-exact",
        "english-singular",
        "english-two-lemmas",
        "case-insensitive",
    ],
)
async def test_search_matches_other_word_forms_and_highlights_them(
    manticore,
    content,
    query,
    snippet,
):
    note_id = await _insert(content)
    await _insert("Совсем другой текст. Unrelated text.")

    found = await manticoresearch.search(query)

    assert found == {
        note_id: manticoresearch.SearchResult(replace_substring=content, snippet=snippet),
    }


async def test_search_requires_every_word_of_the_query(manticore):
    both = await _insert("Dogs chase cats.")
    await _insert("Dogs sleep.")

    assert set(await manticoresearch.search("dog cat")) == {both}


async def test_search_without_matches_is_empty(manticore):
    await _insert(RUSSIAN)

    assert await manticoresearch.search("кошка") == {}


async def test_search_on_an_empty_table_is_empty(manticore):
    assert await manticoresearch.search("dog") == {}


async def test_search_with_an_empty_query_does_not_reach_manticore():
    # no `manticore` fixture: the configured port is unreachable
    assert await manticoresearch.search("") == {}


async def test_search_escapes_an_apostrophe(manticore):
    note_id = await _insert("The dog's bone.")

    assert set(await manticoresearch.search("dog's")) == {note_id}


@pytest.mark.parametrize(
    "query",
    ['"', "(dog", "dog ("],
    ids=["quote", "open-paren", "dangling-paren"],
)
async def test_search_fails_on_unbalanced_query_operators_current_behaviour(
    manticore,
    query,
):
    await _insert(ENGLISH)

    with pytest.raises(manticoresearch.ManticoreException, match="syntax error"):
        await manticoresearch.search(query)


async def test_search_understands_the_manticore_or_operator(manticore):
    dog = await _insert("Dogs sleep.")
    cat = await _insert("Cats sleep.")
    await _insert("Birds sleep.")

    assert set(await manticoresearch.search("dog | cat")) == {dog, cat}


async def test_update_content_replaces_the_indexed_text(manticore):
    note_id = await _insert(ENGLISH)
    other = await _insert("Dogs sleep.")

    await manticoresearch.update_content(
        note_id=note_id,
        content="Cats sleep.",
        added_at=ADDED_AT,
    )

    assert await _stored() == {note_id: "Cats sleep.", other: "Dogs sleep."}
    assert set(await manticoresearch.search("dog")) == {other}
    assert set(await manticoresearch.search("cat")) == {note_id}


async def test_update_content_accepts_the_id_as_a_string(manticore):
    note_id = await _insert(ENGLISH)

    await manticoresearch.update_content(
        note_id=str(note_id),
        content="Cats sleep.",
        added_at=ADDED_AT,
    )

    assert await _stored() == {note_id: "Cats sleep."}


async def test_update_content_of_a_missing_note_inserts_it_current_behaviour(manticore):
    note_id = uuid.uuid4()

    await manticoresearch.update_content(
        note_id=note_id,
        content=ENGLISH,
        added_at=ADDED_AT,
    )

    assert await _stored() == {note_id: ENGLISH}


@pytest.mark.parametrize("as_type", [uuid.UUID, str], ids=["uuid", "str"])
async def test_delete_removes_only_the_given_note(manticore, as_type):
    note_id = await _insert(ENGLISH)
    other = await _insert("Dogs sleep.")

    await manticoresearch.delete(as_type(str(note_id)))

    assert await _stored() == {other: "Dogs sleep."}
    assert set(await manticoresearch.search("dog")) == {other}


async def test_delete_of_a_missing_note_changes_nothing(manticore):
    note_id = await _insert(ENGLISH)

    await manticoresearch.delete(uuid.uuid4())

    assert await _stored() == {note_id: ENGLISH}


async def test_insert_all_without_notes_does_not_reach_manticore():
    await manticoresearch._insert_all()


async def test_init_loads_the_live_notes_from_postgresql(manticore):
    material_id = await factories.insert_material()
    first = await factories.insert_note(material_id=material_id, content=RUSSIAN)
    second = await factories.insert_note(material_id=material_id, content=ENGLISH)
    deleted = await factories.insert_note(
        material_id=material_id,
        content="Deleted dogs.",
    )
    await notes_db.delete_note(note_id=deleted)
    stale = await _insert("Stale dogs from a previous index.")

    await manticoresearch.init()

    assert await _stored() == {first: RUSSIAN, second: ENGLISH}
    assert set(await manticoresearch.search("dog")) == {second}
    assert stale not in await _stored()


async def test_init_on_an_empty_database_leaves_an_empty_table(manticore):
    await _insert(ENGLISH)

    await manticoresearch.init()

    assert await _stored() == {}


async def test_get_notes_returns_the_live_notes():
    material_id = await factories.insert_material()
    note_id = await factories.insert_note(material_id=material_id, content=RUSSIAN)
    deleted = await factories.insert_note(material_id=material_id)
    await notes_db.delete_note(note_id=deleted)
    added_at = (await factories.fetch_row(models.Notes, note_id))["added_at"]

    notes = await manticoresearch._get_notes()

    assert notes == [
        manticoresearch.Note(note_id=note_id, content=RUSSIAN, added_at=added_at),
    ]


async def test_get_notes_on_an_empty_database_is_empty():
    assert await manticoresearch._get_notes() == []


async def test_get_note_returns_the_note():
    material_id = await factories.insert_material()
    await factories.insert_note(material_id=material_id)
    note_id = await factories.insert_note(material_id=material_id, content=ENGLISH)
    added_at = (await factories.fetch_row(models.Notes, note_id))["added_at"]

    note = await manticoresearch._get_note(note_id=note_id)

    assert note == manticoresearch.Note(
        note_id=note_id,
        content=ENGLISH,
        added_at=added_at,
    )


@pytest.mark.parametrize("is_deleted", [False, True], ids=["missing", "deleted"])
async def test_get_note_raises_for_a_note_that_is_not_live(is_deleted):
    note_id = uuid.uuid4()
    if is_deleted:
        note_id = await factories.insert_note(
            material_id=await factories.insert_material(),
        )
        await notes_db.delete_note(note_id=note_id)

    with pytest.raises(ValueError, match=f"Note {note_id} not found"):
        await manticoresearch._get_note(note_id=note_id)


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("dogs", ["**Dogs** are running in the forest."]),
        ("dog", ["**Dogs** are running in the forest."]),
        ("forest run", ["Dogs are **running** in the **forest**."]),
        ("cat", []),
    ],
    ids=["exact", "other-form", "two-words", "no-match"],
)
async def test_autocompletion_returns_highlighted_notes(manticore, query, expected):
    await _insert(ENGLISH)
    await _insert(RUSSIAN)

    assert await manticoresearch.autocompletion(query=query) == expected


async def test_autocompletion_does_not_complete_a_word_prefix_current_behaviour(
    manticore,
):
    await _insert(ENGLISH)

    await _insert(RUSSIAN)

    # the table has no min_prefix_len, so the trailing `*` of the query does not expand
    assert await manticoresearch.autocompletion(query="do") == []
    assert await manticoresearch.autocompletion(query="соба") == []


@pytest.mark.parametrize(("limit", "expected"), [(0, 0), (1, 1), (2, 2), (5, 3)])
async def test_autocompletion_respects_the_limit(manticore, limit, expected):
    for index in range(3):
        await _insert(f"Dogs number {index}.")

    found = await manticoresearch.autocompletion(query="dog", limit=limit)

    assert len(found) == expected
    assert all(snippet.startswith("**Dogs** number") for snippet in found)


async def test_autocompletion_defaults_to_five_results(manticore):
    for index in range(6):
        await _insert(f"Dogs number {index}.")

    assert len(await manticoresearch.autocompletion(query="dog")) == 5


async def test_autocompletion_with_a_negative_limit_returns_garbage_current_behaviour(
    manticore,
):
    await _insert(ENGLISH)

    found = await manticoresearch.autocompletion(query="dog", limit=-1)

    # Manticore answers `LIMIT -1` with a single column that is not the highlighted snippet
    assert len(found) == 1
    assert "**" not in found[0]


AUTOCOMPLETION_BUG = (
    "BUG: tracker/common/manticoresearch.py:213-216 the query is pasted into the statement "
    "with an f-string, so a quote in it ends the MATCH literal"
)


async def test_autocompletion_accepts_an_apostrophe(manticore):
    await _insert("The dog's bone.")

    assert await manticoresearch.autocompletion(query="dog's") == ["The **dog's** bone."]


async def test_autocompletion_cannot_be_used_to_change_the_statement(manticore):
    for index in range(3):
        await _insert(f"Dogs number {index}.")

    # with a bound parameter this is a query that matches nothing, never a second LIMIT clause
    found = await manticoresearch.autocompletion(
        query="dog') LIMIT 3 OPTION ranker=none /*",
        limit=1,
    )

    assert found == []


async def test_cursor_wraps_errors_into_manticore_exception(manticore):
    with pytest.raises(manticoresearch.ManticoreException, match="no_such_table"):
        async with manticoresearch._cursor() as cur:
            await cur.execute("SELECT * FROM no_such_table")


async def test_cursor_wraps_exceptions_raised_inside_the_block(manticore):
    error = RuntimeError("boom")

    with pytest.raises(manticoresearch.ManticoreException) as exc_info:
        async with manticoresearch._cursor():
            raise error

    assert exc_info.value.__cause__ is error


async def test_readiness_follows_the_five_seconds_uptime_rule(manticore):
    async def uptime() -> int:
        async with manticoresearch._cursor() as cur:
            await cur.execute("SHOW STATUS LIKE 'uptime'")
            _, value = await cur.fetchone()
        return int(value)

    before = await uptime()
    is_ready = await manticoresearch.readiness()
    after = await uptime()

    # the container may be younger than five seconds, so the expectation follows its real uptime
    if (before >= READY_UPTIME_SECONDS) == (after >= READY_UPTIME_SECONDS):
        assert is_ready is (before >= READY_UPTIME_SECONDS)
    else:
        assert isinstance(is_ready, bool)


async def test_readiness_is_false_when_manticore_is_unreachable(mocker):
    mocker.patch.object(settings, "MANTICORE_MYSQL_PORT", 1)

    assert await manticoresearch.readiness() is False


async def test_create_table_is_idempotent_and_keeps_the_rows(manticore):
    note_id = await _insert(ENGLISH)

    await manticoresearch._create_table()

    assert await _stored() == {note_id: ENGLISH}


async def test_drop_table_is_idempotent(manticore):
    await manticoresearch._drop_table()
    await manticoresearch._drop_table()

    with pytest.raises(manticoresearch.ManticoreException):
        await _stored()
