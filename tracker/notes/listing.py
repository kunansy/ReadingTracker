import asyncio
import itertools
from collections.abc import Iterable
from typing import Any
from uuid import UUID

from tracker.common import manticoresearch, settings
from tracker.notes import db, schemas


def filter_notes(*, notes: list[db.Note], ids: Iterable[UUID]) -> list[db.Note]:
    notes_ = {note.note_id: note for note in notes}
    return [notes_[note_id] for note_id in ids if note_id in notes_]


def find_tags_intersection(notes: list[db.Note], tags: set[str]) -> set[UUID]:
    return {
        note.note_id
        for note in notes
        if note.tags and note.tags >= tags
    }


def highlight_snippets(
    notes: list[db.Note],
    search_results: dict[UUID, manticoresearch.SearchResult],
) -> None:
    for note in notes:
        result = search_results[note.note_id]
        note.highlight(result.replace_substring, result.snippet)


def limit_notes(notes: list[db.Note], *, page: int, page_size: int) -> list[db.Note]:
    page = max(page, 1)
    page_size = max(page_size, 0)
    return notes[(page - 1) * page_size : page * page_size]


def sort_notes(notes: list[db.Note]) -> list[db.Note]:
    notes = sorted(notes, key=lambda note: note.chapter_int)
    sorted_notes = []
    for _, chapter_notes in itertools.groupby(notes, key=lambda note: note.chapter):
        sorted_notes.extend(sorted(chapter_notes, key=lambda note: note.page))

    return sorted_notes


async def build_notes_search_result(
    *,
    search: schemas.SearchParams,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    material_id = search.material_id
    async with asyncio.TaskGroup() as tg:
        get_notes_task = tg.create_task(db.get_notes(material_id=material_id))
        get_titles_task = tg.create_task(db.get_material_with_notes_titles())
        get_material_types_task = tg.create_task(db.get_material_types())
        get_tags_task = tg.create_task(db.get_sorted_tags(material_id=material_id))
        get_material_notes_task = tg.create_task(db.get_all_notes_count())

    notes = get_notes_task.result()

    if requested_tags := search.requested_tags():
        found_note_ids = find_tags_intersection(notes, requested_tags)
        notes = filter_notes(notes=notes, ids=found_note_ids)
    if query := search.query:
        search_results = await manticoresearch.search(query)
        notes = filter_notes(notes=notes, ids=search_results.keys())
        highlight_snippets(notes, search_results)

    notes[:] = sort_notes(notes)
    chapters = db.get_distinct_chapters(notes)
    total_count = len(notes)
    page_notes = limit_notes(notes, page=page, page_size=page_size)

    return {
        "notes": page_notes,
        "total_count": total_count,
        "titles": get_titles_task.result(),
        "material_types": get_material_types_task.result(),
        "material_notes": get_material_notes_task.result(),
        "chapters": chapters,
        "query": search.query,
        "tags": get_tags_task.result(),
        "tags_query": search.tags_query,
        "current_page": page,
        "page_size": page_size,
        "material_id": material_id,
        "DATE_FORMAT": settings.DATE_FORMAT,
    }
