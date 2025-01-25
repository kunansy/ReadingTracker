import random
import uuid
from itertools import groupby
from typing import NamedTuple
from uuid import UUID

import pytest
import sqlalchemy.sql as sa

from tests.conftest import mock_trans
from tracker.common import database
from tracker.models import enums, models
from tracker.notes import db, routes


async def test_get_distinct_chapters():
    notes = await db.get_notes()

    result = db.get_distinct_chapters(notes)

    expected = {}
    for note in notes:
        if note.chapter not in expected.get(note.material_id, []):
            expected.setdefault(note.material_id, []).append(note.chapter)

    assert result == expected


def test_get_distinct_chapters_empty():
    assert db.get_distinct_chapters([]) == {}


async def test_get_material_type():
    result = await db.get_material_type(
        material_id="ab4d33f3-7602-4fde-afe8-d3fe5876867b",
    )

    assert result == enums.MaterialTypesEnum.audiobook.name


async def test_get_material_type_not_found():
    result = await db.get_material_type(
        material_id="4c753160-3363-47f5-b888-3574809592b0",
    )

    assert result is None


async def test_get_material_types():
    types = await db.get_material_types()
    type_values = set(types.values())

    assert all(enums.MaterialTypesEnum(type_) for type_ in type_values)


async def test_get_material_titles():
    material_titles = await db.get_material_titles()

    stmt = sa.select(sa.func.count(1)).select_from(models.Materials)

    async with database.session() as ses:
        materials_count = await ses.scalar(stmt)

    assert len(material_titles) == materials_count


async def test_get_material_with_notes_titles():
    stmt = (
        sa.select(models.Materials.c.material_id)
        .join(models.Notes)
        .where(~models.Notes.c.is_deleted)
    )

    async with database.session() as ses:
        expected = set((await ses.scalars(stmt)).all())

    titles = await db.get_material_with_notes_titles()

    assert len(titles) == len(expected)
    assert set(titles.keys()) == expected


@pytest.mark.parametrize(
    "material_id",
    [
        UUID("5c66e1ca-eb52-47e5-af50-c48b345c7e6c"),
        None,
    ],
)
async def test_get_notes(material_id: UUID | None):
    notes = await db.get_notes(material_id=material_id)

    assert all(not note.is_deleted for note in notes), "Deleted note found"
    if material_id:
        assert all(
            note.material_id == material_id for note in notes
        ), "Note with wrong material id found"

    stmt = (
        sa.select(sa.func.count(1))  # type: ignore
        .select_from(models.Notes)
        .where(~models.Notes.c.is_deleted)
    )

    if material_id:
        stmt = stmt.where(models.Notes.c.material_id == material_id)

    async with database.session() as ses:
        notes_count = await ses.scalar(stmt) or 0

    assert len(notes) == notes_count, f"Some notes missed, {len(notes)} != {notes_count}"


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


async def test_delete_restore_note():
    note_id = "40824c08-3e86-4fff-8ced-ee90ffee1e6c"
    assert await db.get_note(note_id=note_id) is not None

    await db.delete_note(note_id=note_id)
    assert await db.get_note(note_id=note_id) is None

    await db.restore_note(note_id=note_id)
    assert await db.get_note(note_id=note_id) is not None


@pytest.mark.parametrize(
    "note_id",
    [
        "2febbe11-4513-40f4-b2a7-a3ca51f30a3d",
        "10bfed52-d5bb-4818-a315-c123e45b63c2",
        "27a05123-d89f-4383-973a-f1b3caf476f0",
        "c94e12cc-e773-4993-bf3d-7a1a1400ad3a",
        "7e065063-9e46-498f-90a7-6be47e7833bc",
        "85b8ff0a-c671-454e-8c95-2375bdcdfed0",
        "12782f80-1d5d-4e97-889d-b78bedb33169",
    ],
)
async def test_link_notes(note_id):
    notes = {note.note_id: note for note in await db.get_notes()}

    result = db.link_notes(note_id=UUID(note_id), notes=notes)

    assert len(result.nodes) == 10
    assert len(result.edges) == 9

    assert set(result.edges) == {
        ("c94e12cc-e773-4993-bf3d-7a1a1400ad3a", "27a05123-d89f-4383-973a-f1b3caf476f0"),
        ("10bfed52-d5bb-4818-a315-c123e45b63c2", "639e8583-73af-41b6-9002-29769957a139"),
        ("12782f80-1d5d-4e97-889d-b78bedb33169", "2febbe11-4513-40f4-b2a7-a3ca51f30a3d"),
        ("4f4dd5e9-e5de-46a7-865d-b0646e0878fd", "10bfed52-d5bb-4818-a315-c123e45b63c2"),
        ("85b8ff0a-c671-454e-8c95-2375bdcdfed0", "7e065063-9e46-498f-90a7-6be47e7833bc"),
        ("0eb77170-847b-4e3a-b90f-962012aba333", "85b8ff0a-c671-454e-8c95-2375bdcdfed0"),
        ("7e065063-9e46-498f-90a7-6be47e7833bc", "c94e12cc-e773-4993-bf3d-7a1a1400ad3a"),
        ("639e8583-73af-41b6-9002-29769957a139", "2febbe11-4513-40f4-b2a7-a3ca51f30a3d"),
        ("27a05123-d89f-4383-973a-f1b3caf476f0", "4f4dd5e9-e5de-46a7-865d-b0646e0878fd"),
    }


@pytest.mark.parametrize(
    "note_id",
    ["1ca65e74-d435-4de7-ad23-95cefba35bd1", "d6d27e4f-7748-41c9-90db-dd35f0189d36"],
)
async def test_link_notes_without_links(note_id):
    notes = {note.note_id: note for note in await db.get_notes()}

    result = db.link_notes(note_id=UUID(note_id), notes=notes)

    assert len(result.nodes) == 1
    assert len(result.edges) == 0


@pytest.mark.parametrize(
    "material_id",
    [
        None,  # empty list
        # "",  # all notes # TODO: WTF?
        "539ef05c-1705-4ddb-9c4a-7e2f85ecc39f",  # notes for the material
        "62d6ab19-6431-4eb4-a526-07774a4bc2e4",  # notes for the material without links
    ],
)
async def test_link_all_notes(material_id: str | None):
    if material_id is None:
        notes = []
    else:
        notes = await db.get_notes(material_id=material_id)

    graph = db.link_all_notes(notes)

    assert len(graph.nodes) == len(notes), "Nodes count is wrong"
    assert len(graph.edges) == sum(
        1 for note in notes if note.link_id
    ), "Edges count is wrong"


async def test_create_graphic():
    notes = await db.get_notes()

    graph = db.link_all_notes(notes)
    graphic_html = db.create_graphic(graph)

    assert graphic_html, "Empty html"
    assert graphic_html.startswith("<html>")


@pytest.mark.skip()
async def test_get_sorted_tags():
    material_id = "38e13f37-9d28-4c68-80b2-2bfdf6567372"
    material_tags = await db._get_tags(material_id=material_id)
    tags = await db._get_tags()

    test_result = await db.get_sorted_tags(material_id=material_id)

    assert len(tags) >= len(material_tags)
    assert len(tags) == len(test_result)

    assert sorted(test_result[: len(material_tags)]) == sorted(material_tags)


async def test_get_sorted_tags_without_material():
    tags = await db._get_tags()

    result = await db.get_sorted_tags(material_id=None)

    assert result == sorted(tags)


@pytest.mark.parametrize(
    ("note_id", "expected"),
    [
        (
                "3ad7a635-2057-4050-a874-471e001f86aa",
                [
                    "31e8bb75-70e2-4a5b-92fd-722837cf1f79",
                    "058f4c4d-c4af-4e73-a142-177e77afd51e",
                ],
        ),
        (
                "ff05baa2-b73d-41fc-899e-7daa95b687c6",
                ["d205a2d6-f288-4eb9-8441-13b605371e92"],
        ),
        ("a5386aee-a186-4e6f-abaa-63853c75cce4", []),
    ],
)
async def test_get_links_from(note_id, expected):
    expected_notes = [await db.get_note(note_id=exp_note_id) for exp_note_id in expected]

    result = await db.get_links_from(note_id=UUID(note_id))
    assert result == expected_notes


@pytest.mark.parametrize(
    ("lst", "page", "page_size", "expected"),
    [
        (list(range(100)), 1, 10, [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]),
        (list(range(100)), 2, 10, [10, 11, 12, 13, 14, 15, 16, 17, 18, 19]),
        (list(range(100)), 3, 10, [20, 21, 22, 23, 24, 25, 26, 27, 28, 29]),
        (list(range(100)), 0, 10, [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]),
        (list(range(100)), -5, 10, [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]),
        (list(range(100)), 1, -5, []),
        (list(range(5)), 1, 10, [0, 1, 2, 3, 4]),
        (list(range(5)), 2, 10, []),
        ([], 1, 10, []),
    ],
)
def test_notes_limit(lst, page, page_size, expected):
    assert routes._limit_notes(lst, page=page, page_size=page_size) == expected


@pytest.mark.parametrize(
    ("sample", "expected"),
    [
        ((
                 (12, "1.2", 5), (12, "1.2", 2), (12, "1.2", 17), (12, "1.2", 0), (12, "1.2", 5),
                 (4, "4", 5), (4, "4", 2), (4, "4", 17), (4, "4", 0), (4, "4", 5),
                 (23, "2.3", 5), (23, "2.3", 2), (23, "2.3", 17), (23, "2.3", 0), (23, "2.3", 5),
                 (10, "1.0", 5), (10, "1.0", 2), (10, "1.0", 17), (10, "1.0", 0), (10, "1.0", 5),
                 (9, "9", 5), (9, "9", 2), (9, "9", 17), (9, "9", 0), (9, "9", 5),
         ),
         (
                 (4, "4", 0), (4, "4", 2), (4, "4", 5), (4, "4", 5), (4, "4", 17),
                 (9, "9", 0), (9, "9", 2), (9, "9", 5), (9, "9", 5), (9, "9", 17),
                 (10, "1.0", 0), (10, "1.0", 2), (10, "1.0", 5), (10, "1.0", 5), (10, "1.0", 17),
                 (12, "1.2", 0), (12, "1.2", 2), (12, "1.2", 5), (12, "1.2", 5), (12, "1.2", 17),
                 (23, "2.3", 0), (23, "2.3", 2), (23, "2.3", 5), (23, "2.3", 5), (23, "2.3", 17),
         ),)

    ]
)
def test_sort_notes(sample, expected):
    class Note(NamedTuple):
        chapter_int: int
        chapter: str
        page: int

    sample = [
        Note(
            chapter_int=chapter_int,
            chapter=chapter,
            page=page
        )
        for (chapter_int, chapter, page) in sample
    ]
    expected = [
        Note(
            chapter_int=chapter_int,
            chapter=chapter,
            page=page
        )
        for (chapter_int, chapter, page) in expected
    ]
    assert routes._sort_notes(sample) == expected


@pytest.mark.parametrize(
    "material_id, link_id, title, content, chapter, page, tags", (
        (
            UUID("888b717e-4559-4861-8013-ca581cbf0524"),
            None,
            "t",
            "ststst",
            "32 chapter",
            42,
            ["1", "2", "3"]
        ),
        (
            UUID("888b717e-4559-4861-8013-ca581cbf0524"),
            UUID("1edc3d70-2607-63cf-8b05-a63a662bdf9f"),
            "t",
            "ststst",
            "32 chapter",
            42,
            ["1", "2", "3"]
        ),
        (
            UUID("888b717e-4559-4861-8013-ca581cbf0524"),
            None,
            "t",
            "asdasd",
            "32 chapter",
            42,
            ["1", "2", "3"]
        ),
        (
            UUID("888b717e-4559-4861-8013-ca581cbf0524"),
            None,
            None,
            "asdfadsf",
            "32 chapter",
            42,
            []
        ),
        (
            UUID("888b717e-4559-4861-8013-ca581cbf0524"),
            None,
            None,
            "dfsadfsd",
            "32 chapter",
            42,
            None,
        ),
        (
            UUID("888b717e-4559-4861-8013-ca581cbf0524"),
            None,
            "1",
            "asdfadsf",
            "32 chapter",
            42,
            ["1"],
        ),
        (
            UUID("888b717e-4559-4861-8013-ca581cbf0524"),
            None,
            "1",
            "asdfadsf",
            "",
            0,
            ["1"],
        ),
    )
)
async def test_insert_note(mocker, material_id, link_id, title, content, chapter, page, tags):
    old_notes_count = await db.get_all_notes_count()

    mocker.patch(
        "tracker.notes.db.database.session",
        mock_trans
    )

    note_id = await db.add_note(
        material_id=material_id,
        link_id=link_id,
        title=title,
        content=content,
        chapter=chapter,
        page=page,
        tags=tags
    )

    UUID(note_id)

    assert old_notes_count == await db.get_all_notes_count()


async def test_is_deleted_false():
    notes = await db.get_notes()
    assert len(notes) > 0

    note = random.choice(notes)

    is_deleted = await db.is_deleted(note.note_id)
    assert not is_deleted


async def test_is_deleted_true():
    deleted_notes_stmt = (sa.select(models.Notes.c.note_id)
                     .where(models.Notes.c.is_deleted))

    async with database.session() as ses:
        deleted_notes = (await ses.execute(deleted_notes_stmt)).all()

    assert len(deleted_notes) > 0
    note_id, = random.choice(deleted_notes)

    is_deleted = await db.is_deleted(note_id)
    assert is_deleted


async def test_is_deleted_not_found():
    id = str(uuid.uuid4())

    with pytest.raises(database.DatabaseException) as e:
        await db.is_deleted(id)

    assert e.type is database.DatabaseException
    assert str(e.value) == f"Note id={id} not found"
