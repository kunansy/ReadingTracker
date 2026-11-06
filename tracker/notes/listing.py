import asyncio
from typing import Any
from uuid import UUID

from tracker.common import manticoresearch, pagination, settings
from tracker.notes import db, schemas


def highlight_snippets(
    notes: list[db.Note],
    search_results: dict[UUID, manticoresearch.SearchResult],
) -> None:
    for note in notes:
        result = search_results[note.note_id]
        note.highlight(result.replace_substring, result.snippet)


async def build_notes_search_result(
    *,
    search: schemas.SearchParams,
    params: pagination.PageParams,
) -> dict[str, Any]:
    material_id = search.material_id
    requested_tags = search.requested_tags()

    search_results = None
    if query := search.query:
        search_results = await manticoresearch.search(query)
    note_ids = search_results.keys() if search_results is not None else None

    async with asyncio.TaskGroup() as tg:
        get_notes_task = tg.create_task(
            db.search_notes_page(
                material_id=material_id,
                tags=requested_tags,
                note_ids=note_ids,
                params=params,
            ),
        )
        get_chapters_task = tg.create_task(
            db.get_distinct_chapters(
                material_id=material_id,
                tags=requested_tags,
                note_ids=note_ids,
            ),
        )
        get_titles_task = tg.create_task(db.get_material_with_notes_titles())
        get_material_types_task = tg.create_task(db.get_material_types())
        get_tags_task = tg.create_task(db.get_sorted_tags(material_id=material_id))
        get_material_notes_task = tg.create_task(db.get_all_notes_count())

    page = get_notes_task.result()
    if search_results is not None:
        highlight_snippets(page.items, search_results)

    return {
        "notes": page.items,
        "total_count": page.total_count,
        "next_token": page.next_token,
        "titles": get_titles_task.result(),
        "material_types": get_material_types_task.result(),
        "material_notes": get_material_notes_task.result(),
        "chapters": get_chapters_task.result(),
        "query": search.query,
        "tags": get_tags_task.result(),
        "tags_query": search.tags_query,
        "page_size": params.page_size,
        "material_id": material_id,
        "DATE_FORMAT": settings.DATE_FORMAT,
    }
