from uuid import UUID

import pytest

from tests.unit.api import factories
from tracker.common import manticoresearch, pagination
from tracker.notes import db as notes_db, listing, schemas


def _result(replace_substring: str, snippet: str) -> manticoresearch.SearchResult:
    return manticoresearch.SearchResult(
        replace_substring=replace_substring, snippet=snippet
    )


def test_highlight_snippets_replaces_the_matched_substring_in_every_note():
    first = factories.note(content="про войну и мир")
    second = factories.note(note_id=factories.OTHER_NOTE_ID, content="war and war")
    results = {
        first.note_id: _result("войну", "<b>войну</b>"),
        second.note_id: _result("war", "<b>war</b>"),
    }

    listing.highlight_snippets([first, second], results)

    assert first.content == "про <b>войну</b> и мир"
    assert second.content == "<b>war</b> and <b>war</b>"


def test_highlight_snippets_leaves_content_without_the_substring_untouched():
    note = factories.note(content="nothing to see")

    listing.highlight_snippets([note], {note.note_id: _result("absent", "<b>absent</b>")})

    assert note.content == "nothing to see"


def test_highlight_snippets_ignores_results_of_notes_outside_the_page():
    listing.highlight_snippets([], {factories.NOTE_ID: _result("a", "b")})


def test_highlight_snippets_fails_on_a_note_without_a_result_current_behaviour():
    note = factories.note()

    with pytest.raises(KeyError):
        listing.highlight_snippets([note], {})


SIDE_QUERIES = {
    "get_distinct_chapters": {factories.MATERIAL_ID: ["1", "2"]},
    "get_material_with_notes_titles": {factories.MATERIAL_ID: "Война и мир"},
    "get_material_types": {factories.MATERIAL_ID: "book"},
    "get_sorted_tags": ["tag"],
    "get_all_notes_count": {factories.MATERIAL_ID: 2},
}


@pytest.fixture
def db_mocks(mocker):
    mocks = {
        name: mocker.patch.object(notes_db, name, mocker.AsyncMock(return_value=value))
        for name, value in SIDE_QUERIES.items()
    }
    mocks["search_notes_page"] = mocker.patch.object(
        notes_db,
        "search_notes_page",
        mocker.AsyncMock(return_value=factories.page()),
    )
    return mocks


async def test_search_without_query_skips_full_text_search(mocker, db_mocks):
    search = mocker.patch.object(manticoresearch, "search", mocker.AsyncMock())
    note = factories.note()
    db_mocks["search_notes_page"].return_value = pagination.Page(
        items=[note], next_token="next", total_count=21
    )
    params = pagination.PageParams(page_size=1)

    result = await listing.build_notes_search_result(
        search=schemas.SearchParams(
            material_id=factories.MATERIAL_ID, tags_query=" b  a b "
        ),
        params=params,
    )

    search.assert_not_awaited()
    assert result == {
        "notes": [note],
        "total_count": 21,
        "next_token": "next",
        "titles": {factories.MATERIAL_ID: "Война и мир"},
        "material_types": {factories.MATERIAL_ID: "book"},
        "material_notes": {factories.MATERIAL_ID: 2},
        "chapters": {factories.MATERIAL_ID: ["1", "2"]},
        "query": None,
        "tags": ["tag"],
        "tags_query": "b  a b",
        "page_size": 1,
        "material_id": factories.MATERIAL_ID,
        "DATE_FORMAT": "%Y-%m-%d",
    }
    assert note.content == "Content #tag"
    db_mocks["search_notes_page"].assert_awaited_once_with(
        material_id=factories.MATERIAL_ID,
        query=None,
        tags={"a", "b"},
        note_ids=None,
        params=params,
    )
    db_mocks["get_distinct_chapters"].assert_awaited_once_with(
        material_id=factories.MATERIAL_ID, tags={"a", "b"}, note_ids=None
    )
    db_mocks["get_sorted_tags"].assert_awaited_once_with(
        material_id=factories.MATERIAL_ID
    )
    db_mocks["get_material_with_notes_titles"].assert_awaited_once_with()
    db_mocks["get_material_types"].assert_awaited_once_with()
    db_mocks["get_all_notes_count"].assert_awaited_once_with()


@pytest.mark.parametrize("query", [None, ""], ids=["none", "empty"])
async def test_search_treats_an_empty_query_as_no_query(mocker, db_mocks, query):
    search = mocker.patch.object(manticoresearch, "search", mocker.AsyncMock())

    result = await listing.build_notes_search_result(
        search=schemas.SearchParams(query=query), params=pagination.PageParams()
    )

    search.assert_not_awaited()
    assert result["query"] == query
    assert result["material_id"] is None
    assert result["page_size"] == pagination.DEFAULT_PAGE_SIZE
    kwargs = db_mocks["search_notes_page"].await_args.kwargs
    assert kwargs["note_ids"] is None
    assert kwargs["tags"] == set()


async def test_search_with_query_filters_by_found_ids_and_highlights(mocker, db_mocks):
    found = factories.note(content="about war")
    other_id = UUID("77777777-7777-4777-8777-777777777777")
    search = mocker.patch.object(
        manticoresearch,
        "search",
        mocker.AsyncMock(
            return_value={
                found.note_id: _result("war", "<b>war</b>"),
                other_id: _result("war", "<b>war</b>"),
            },
        ),
    )
    db_mocks["search_notes_page"].return_value = factories.page([found])

    result = await listing.build_notes_search_result(
        search=schemas.SearchParams(query="war"), params=pagination.PageParams()
    )

    search.assert_awaited_once_with("war")
    assert result["query"] == "war"
    assert [n.content for n in result["notes"]] == ["about <b>war</b>"]
    page_kwargs = db_mocks["search_notes_page"].await_args.kwargs
    assert page_kwargs["query"] == "war"
    assert list(page_kwargs["note_ids"]) == [found.note_id, other_id]
    chapters_kwargs = db_mocks["get_distinct_chapters"].await_args.kwargs
    assert list(chapters_kwargs["note_ids"]) == [found.note_id, other_id]


async def test_search_with_query_that_matches_nothing_passes_an_empty_filter(
    mocker, db_mocks
):
    mocker.patch.object(manticoresearch, "search", mocker.AsyncMock(return_value={}))

    result = await listing.build_notes_search_result(
        search=schemas.SearchParams(query="absent"), params=pagination.PageParams()
    )

    note_ids = db_mocks["search_notes_page"].await_args.kwargs["note_ids"]
    assert note_ids is not None
    assert list(note_ids) == []
    assert result["notes"] == []
    assert result["total_count"] == 0
    assert result["next_token"] is None


async def test_search_does_not_query_the_database_when_full_text_search_fails(
    mocker, db_mocks
):
    mocker.patch.object(
        manticoresearch,
        "search",
        mocker.AsyncMock(side_effect=manticoresearch.ManticoreException("down")),
    )

    with pytest.raises(manticoresearch.ManticoreException, match="down"):
        await listing.build_notes_search_result(
            search=schemas.SearchParams(query="war"), params=pagination.PageParams()
        )

    for mock in db_mocks.values():
        mock.assert_not_awaited()
