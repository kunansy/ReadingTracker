from itertools import groupby

import pytest
import sqlalchemy.sql as sa

from tracker.common import database
from tracker.models import enums, models
from tracker.notes import db


@pytest.mark.asyncio
async def test_get_distinct_chapters():
    notes = await db.get_notes()

    result = db.get_distinct_chapters(notes)

    expected = {}
    for note in notes:
        expected[note.material_id] = expected.get(note.material_id, set()) | {note.chapter}

    assert result == expected


def test_get_distinct_chapters_empty():
    assert db.get_distinct_chapters([]) == {}


@pytest.mark.asyncio
async def test_get_material_type():
    result = await db.get_material_type(material_id="ab4d33f3-7602-4fde-afe8-d3fe5876867b")

    assert result == enums.MaterialTypesEnum.audiobook.name


@pytest.mark.asyncio
async def test_get_material_type_not_found():
    result = await db.get_material_type(material_id="4c753160-3363-47f5-b888-3574809592b0")

    assert result is None


@pytest.mark.asyncio
async def test_get_material_types():
    types = await db.get_material_types()
    type_values = set(types.values())

    assert all(enums.MaterialTypesEnum(type_) for type_ in type_values)


@pytest.mark.asyncio
async def test_get_material_titles():
    material_titles = await db.get_material_titles()

    stmt = sa.select(sa.func.count(1)) \
        .select_from(models.Materials)

    async with database.session() as ses:
        materials_count = await ses.scalar(stmt)

    assert len(material_titles) == materials_count


@pytest.mark.asyncio
async def test_get_material_with_notes_titles():
    stmt = sa.select(models.Materials.c.material_id)\
        .join(models.Notes,
              models.Notes.c.material_id == models.Materials.c.material_id)\
        .where(~models.Notes.c.is_deleted)

    async with database.session() as ses:
        expected = set((await ses.scalars(stmt)).all())

    titles = await db.get_material_with_notes_titles()

    assert len(titles) == len(expected)
    assert set(titles.keys()) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'material_id', (
        "5c66e1ca-eb52-47e5-af50-c48b345c7e6c",
        None,
    )
)
async def test_get_notes(material_id: str | None):
    notes = await db.get_notes(material_id=material_id)

    assert all(not note.is_deleted for note in notes), "Deleted note found"
    if material_id:
        assert all(note.material_id == material_id for note in notes), "Note with wrong material id found"

    stmt = sa.select(sa.func.count(1)) \
        .select_from(models.Notes) \
        .where(~models.Notes.c.is_deleted)

    if material_id:
        stmt = stmt.where(models.Notes.c.material_id == material_id)

    async with database.session() as ses:
        notes_count = await ses.scalar(stmt)

    assert len(notes) == notes_count, f"Some notes missed, {len(notes)} != {len(notes_count)}"


@pytest.mark.asyncio
async def test_get_all_notes_count():
    notes = await db.get_notes()
    notes.sort(key=lambda note: note.material_id)

    notes_count = {
        material_id: len(list(group))
        for material_id, group in groupby(notes, key=lambda note: note.material_id)
    }

    test_result = await db.get_all_notes_count()

    assert notes_count == test_result
    assert len(notes) == sum(test_result.values())


@pytest.mark.asyncio
async def test_delete_restore_note():
    note_id = "40824c08-3e86-4fff-8ced-ee90ffee1e6c"
    assert await db.get_note(note_id=note_id) is not None

    await db.delete_note(note_id=note_id)
    assert await db.get_note(note_id=note_id) is None

    await db.restore_note(note_id=note_id)
    assert await db.get_note(note_id=note_id) is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "note_id", (
        "2febbe11-4513-40f4-b2a7-a3ca51f30a3d",
        "10bfed52-d5bb-4818-a315-c123e45b63c2",
        "27a05123-d89f-4383-973a-f1b3caf476f0",
        "c94e12cc-e773-4993-bf3d-7a1a1400ad3a",
        "7e065063-9e46-498f-90a7-6be47e7833bc",
        "85b8ff0a-c671-454e-8c95-2375bdcdfed0",
        "12782f80-1d5d-4e97-889d-b78bedb33169"
    )
)
async def test_link_notes(note_id):
    notes = {
        note.note_id: note
        for note in await db.get_notes()
    }

    result = db.link_notes(note_id=note_id, notes=notes)

    assert len(result.nodes) == 7
    assert len(result.edges) == 6

    assert set(result.edges) == {
        ('85b8ff0a-c671-454e-8c95-2375bdcdfed0', '27a05123-d89f-4383-973a-f1b3caf476f0'),
        ('27a05123-d89f-4383-973a-f1b3caf476f0', '2febbe11-4513-40f4-b2a7-a3ca51f30a3d'),
        ('10bfed52-d5bb-4818-a315-c123e45b63c2', '2febbe11-4513-40f4-b2a7-a3ca51f30a3d'),
        ('c94e12cc-e773-4993-bf3d-7a1a1400ad3a', '27a05123-d89f-4383-973a-f1b3caf476f0'),
        ('7e065063-9e46-498f-90a7-6be47e7833bc', 'c94e12cc-e773-4993-bf3d-7a1a1400ad3a'),
        ('12782f80-1d5d-4e97-889d-b78bedb33169', '2febbe11-4513-40f4-b2a7-a3ca51f30a3d')
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "note_id", (
        "1ca65e74-d435-4de7-ad23-95cefba35bd1",
        "d6d27e4f-7748-41c9-90db-dd35f0189d36"
    )
)
async def test_link_notes_without_links(note_id):
    notes = {
        note.note_id: note
        for note in await db.get_notes()
    }

    result = db.link_notes(note_id=note_id, notes=notes)

    assert len(result.nodes) == 1
    assert len(result.edges) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "material_id", (
        None,  # empty list
        "",  # all notes
        "539ef05c-1705-4ddb-9c4a-7e2f85ecc39f",  # notes for the material
        "62d6ab19-6431-4eb4-a526-07774a4bc2e4",  # notes for the material without links
    )
)
async def test_link_all_notes(material_id: str | None):
    if material_id is None:
        notes = []
    else:
        notes = await db.get_notes(material_id=material_id)

    graph = db.link_all_notes(notes)

    assert len(graph.nodes) == len(notes), "Nodes count is wrong"
    assert len(graph.edges) == sum(1 for note in notes if note.link_id), \
        "Edges count is wrong"


@pytest.mark.asyncio
async def test_create_graphic():
    notes = await db.get_notes()

    graph = db.link_all_notes(notes)
    graphic_html = db.create_graphic(graph)

    assert graphic_html, "Empty html"
    assert graphic_html.startswith("<html>")


@pytest.mark.asyncio
async def test_get_sorted_tags():
    material_id = "38e13f37-9d28-4c68-80b2-2bfdf6567372"
    material_tags = await db.get_tags(material_id=material_id)
    tags = await db.get_tags()

    test_result = await db.get_sorted_tags(material_id=material_id)

    assert len(tags) >= len(material_tags)
    assert len(tags) == len(test_result)

    assert sorted(test_result[:len(material_tags)]) == sorted(material_tags)


@pytest.mark.asyncio
async def test_get_sorted_tags_without_material():
    tags = await db.get_tags()

    result = await db.get_sorted_tags(material_id=None)

    assert result == sorted(tags)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "note_id,expected", (
        ("3ad7a635-2057-4050-a874-471e001f86aa", ["058f4c4d-c4af-4e73-a142-177e77afd51e",
                                                  "31e8bb75-70e2-4a5b-92fd-722837cf1f79",
                                                  "f43b2f9e-cf69-4e62-9f28-b51ca6946636"]),
        ("ff05baa2-b73d-41fc-899e-7daa95b687c6", ["d205a2d6-f288-4eb9-8441-13b605371e92"]),
        ("a5386aee-a186-4e6f-abaa-63853c75cce4", []),
    )
)
async def test_get_links_from(note_id, expected):
    expected_notes = [
        await db.get_note(note_id=exp_note_id)
        for exp_note_id in expected
    ]

    result = await db.get_links_from(note_id=note_id)
    assert result == expected_notes
