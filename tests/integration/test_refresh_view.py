import asyncio
import importlib
import sys
import uuid
from types import ModuleType

import pytest
import sqlalchemy.sql as sa

from tests.integration import (
    factories,
    helpers_notes as helpers,
)
from tracker.common import database
from tracker.materials import db as materials_db
from tracker.models import enums
from tracker.notes import db as notes_db


MATVIEW_COLUMNS = (
    "note_id, material_id, material_title, material_authors, material_type, content, "
    "chapter, page, tags, material_pages, total_notes_count, min_repeat_freq, "
    "material_status, repeated_at, repeats_count"
)


@pytest.fixture
def refresh_view_module(mocker) -> ModuleType:
    """kafka.refresh_view without the asyncio.run() it performs at import time."""
    run = mocker.patch.object(asyncio, "run")
    sys.modules.pop("kafka.refresh_view", None)
    try:
        module = importlib.import_module("kafka.refresh_view")
        assert run.call_count == 1
        [coroutine] = run.call_args.args
        assert coroutine.cr_code is module.refresh_view.__code__
        coroutine.close()
        return module
    finally:
        sys.modules.pop("kafka.refresh_view", None)


async def _matview() -> dict[uuid.UUID, dict]:
    rows = await helpers.fetch_all(f"SELECT {MATVIEW_COLUMNS} FROM mvw_repeat_notes")  # noqa: S608
    return {row.note_id: dict(row._mapping) for row in rows}


async def test_import_runs_refresh_view_once(refresh_view_module):
    assert asyncio.iscoroutinefunction(refresh_view_module.refresh_view)
    assert str(refresh_view_module.REFRESH_REPEAT_NOTES_STMT) == (
        "REFRESH MATERIALIZED VIEW mvw_repeat_notes;"
    )


async def test_refresh_view_makes_new_notes_visible(refresh_view_module):
    material_id = await factories.insert_material()
    note_id = await factories.insert_note(material_id=material_id)
    await factories.refresh_repeat_notes_matview()
    late_note_id = await factories.insert_note(material_id=material_id)
    stale = await _matview()

    await refresh_view_module.refresh_view()

    assert set(stale) == {note_id}
    assert set(await _matview()) == {note_id, late_note_id}


async def test_refresh_view_on_an_empty_database_gives_an_empty_view(refresh_view_module):
    await refresh_view_module.refresh_view()

    assert await _matview() == {}


async def test_matview_row_carries_the_note_and_its_material():
    material_id = await factories.insert_material(
        title="Война и мир",
        authors="Лев Толстой",
        pages=1300,
        material_type=enums.MaterialTypesEnum.audiobook,
    )
    note_id = await factories.insert_note(
        material_id=material_id,
        content="Содержимое.",
        chapter="3",
        page=14,
        tags=["тег", "tag"],
    )

    await factories.refresh_repeat_notes_matview()

    assert await _matview() == {
        note_id: {
            "note_id": note_id,
            "material_id": material_id,
            "material_title": "Война и мир",
            "material_authors": "Лев Толстой",
            "material_type": "audiobook",
            "content": "Содержимое.",
            "chapter": "3",
            "page": 14,
            "tags": ["тег", "tag"],
            "material_pages": 1300,
            "total_notes_count": 1,
            "min_repeat_freq": 0,
            "material_status": "queue",
            "repeated_at": None,
            "repeats_count": None,
        },
    }


async def test_matview_status_follows_the_material_state():
    queued = await factories.insert_note(material_id=await factories.insert_material())
    reading = await factories.insert_note(material_id=await factories.start_material())
    completed = await factories.insert_note(
        material_id=await factories.complete_material(),
    )
    orphan = await factories.insert_note(material_id=uuid.uuid4())

    await factories.refresh_repeat_notes_matview()

    view = await _matview()
    assert {note_id: row["material_status"] for note_id, row in view.items()} == {
        queued: "queue",
        reading: "reading",
        completed: "completed",
        orphan: "completed",
    }
    assert view[orphan]["material_id"] is None
    assert view[orphan]["material_title"] is None
    assert {row["total_notes_count"] for row in view.values()} == {4}


async def test_matview_excludes_deleted_notes_from_rows_and_from_the_total():
    material_id = await factories.insert_material()
    kept = await factories.insert_note(material_id=material_id)
    deleted = await factories.insert_note(material_id=material_id)
    await notes_db.delete_note(note_id=deleted)

    await factories.refresh_repeat_notes_matview()

    view = await _matview()
    assert set(view) == {kept}
    assert view[kept]["total_notes_count"] == 1


async def test_matview_joins_the_material_repeats_only_for_started_materials():
    completed_material = await factories.complete_material()
    queued_material = await factories.insert_material()
    completed_note = await factories.insert_note(material_id=completed_material)
    queued_note = await factories.insert_note(material_id=queued_material)
    for material_id in (completed_material, queued_material):
        await helpers.insert_repeat(
            material_id=material_id,
            repeated_at=helpers.at(helpers.day(-10), 8),
        )
        await helpers.insert_repeat(
            material_id=material_id,
            repeated_at=helpers.at(helpers.day(-3), 9),
        )

    await factories.refresh_repeat_notes_matview()

    view = await _matview()
    assert view[completed_note]["repeated_at"] == helpers.at(helpers.day(-3), 9)
    assert view[completed_note]["repeats_count"] == 2
    assert view[queued_note]["repeated_at"] is None
    assert view[queued_note]["repeats_count"] is None


async def test_matview_keeps_only_notes_never_repeated_while_any_exist():
    material_id = await factories.insert_material()
    never_repeated = await factories.insert_note(material_id=material_id)
    also_never_repeated = await factories.insert_note(material_id=material_id)
    repeated = await factories.insert_note(material_id=material_id)
    await helpers.insert_note_repeat(
        note_id=repeated,
        repeated_at=helpers.at(helpers.day(-400)),
    )

    await factories.refresh_repeat_notes_matview()

    view = await _matview()
    assert set(view) == {never_repeated, also_never_repeated}
    assert {row["total_notes_count"] for row in view.values()} == {3}


async def test_matview_keeps_the_notes_last_repeated_on_the_oldest_day():
    material_id = await factories.insert_material()
    january = await factories.insert_note(material_id=material_id)
    also_january = await factories.insert_note(material_id=material_id)
    february = await factories.insert_note(material_id=material_id)
    repeated_again = await factories.insert_note(material_id=material_id)
    january_day = helpers.FROZEN_TODAY.replace(month=1, day=10)
    february_day = helpers.FROZEN_TODAY.replace(month=2, day=1)
    await helpers.insert_note_repeat(
        note_id=january,
        repeated_at=helpers.at(january_day, 1),
    )
    await helpers.insert_note_repeat(
        note_id=also_january,
        repeated_at=helpers.at(january_day, 23),
    )
    await helpers.insert_note_repeat(
        note_id=february,
        repeated_at=helpers.at(february_day),
    )
    # its last repeat is in February, the January one no longer counts
    await helpers.insert_note_repeat(
        note_id=repeated_again,
        repeated_at=helpers.at(january_day),
    )
    await helpers.insert_note_repeat(
        note_id=repeated_again,
        repeated_at=helpers.at(february_day, 5),
    )

    await factories.refresh_repeat_notes_matview()

    assert set(await _matview()) == {january, also_january}


async def test_matview_groups_by_day_and_prefers_the_smaller_group_current_behaviour():
    material_id = await factories.insert_material()
    january_day = helpers.FROZEN_TODAY.replace(month=1, day=10)
    for _ in range(2):
        note_id = await factories.insert_note(material_id=material_id)
        await helpers.insert_note_repeat(
            note_id=note_id,
            repeated_at=helpers.at(january_day),
        )
    later_in_january = await factories.insert_note(material_id=material_id)
    await helpers.insert_note_repeat(
        note_id=later_in_january,
        repeated_at=helpers.at(january_day.replace(day=20)),
    )

    await factories.refresh_repeat_notes_matview()

    # GROUP BY date binds to the input column (a day), not to the DATE_TRUNC('month') alias,
    # while ORDER BY date binds to the alias: days of one month tie and the smaller group wins
    assert set(await _matview()) == {later_in_january}


async def test_matview_ignores_the_repeat_history_of_deleted_notes():
    material_id = await factories.insert_material()
    live = await factories.insert_note(material_id=material_id)
    deleted = await factories.insert_note(material_id=material_id)
    await helpers.insert_note_repeat(
        note_id=live,
        repeated_at=helpers.at(helpers.day(-5)),
    )
    await helpers.insert_note_repeat(
        note_id=deleted,
        repeated_at=helpers.at(helpers.day(-500)),
    )
    await notes_db.delete_note(note_id=deleted)

    await factories.refresh_repeat_notes_matview()

    assert set(await _matview()) == {live}


async def test_matview_is_empty_when_the_oldest_history_has_no_note_current_behaviour():
    note_id = await factories.insert_note(material_id=await factories.insert_material())
    await helpers.insert_note_repeat(
        note_id=note_id,
        repeated_at=helpers.at(helpers.day(-5)),
    )
    await helpers.insert_note_repeat(
        note_id=uuid.uuid4(),
        repeated_at=helpers.at(helpers.day(-500)),
    )

    await factories.refresh_repeat_notes_matview()

    # the orphan history row forms the oldest group, and that group has no note to show
    assert await _matview() == {}


async def test_matview_reflects_a_material_started_after_the_previous_refresh():
    material_id = await factories.insert_material()
    note_id = await factories.insert_note(material_id=material_id)
    await factories.refresh_repeat_notes_matview()
    before = (await _matview())[note_id]["material_status"]

    await materials_db.start_material(material_id=material_id)
    await factories.refresh_repeat_notes_matview()

    assert before == "queue"
    assert (await _matview())[note_id]["material_status"] == "reading"


async def test_refresh_view_fails_when_the_view_is_missing(refresh_view_module):
    await helpers.execute(sa.text("DROP MATERIALIZED VIEW mvw_repeat_notes"))
    try:
        with pytest.raises(database.DatabaseException, match="mvw_repeat_notes"):
            await refresh_view_module.refresh_view()
    finally:
        await helpers.execute(sa.text(database.REPEAT_NOTES_MATVIEW_QUERY))
        await factories.refresh_repeat_notes_matview()
