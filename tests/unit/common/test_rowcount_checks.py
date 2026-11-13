import datetime
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import UUID

import pytest

from tracker.cards import db as cards_db
from tracker.common import database
from tracker.materials import db as materials_db
from tracker.models import enums
from tracker.notes import db as notes_db
from tracker.reading_log import db as reading_log_db


MATERIAL_ID = UUID("018e9dbe-1d3d-7a5a-b437-9bfa65171b42")
ENTITY_ID = UUID("1c2fc59d-5313-4615-9290-e8668abe2fc0")


class _ZeroRowcountSession:
    async def execute(self, _stmt):
        return SimpleNamespace(rowcount=0)

    def in_transaction(self) -> bool:
        return True


@pytest.fixture
def zero_rowcount_session(mocker):
    @asynccontextmanager
    async def _session(**_kwargs):
        yield _ZeroRowcountSession()

    mocker.patch("tracker.common.database.session", _session)


INSERTS = {
    "card": (
        lambda: cards_db.add_card(
            material_id=MATERIAL_ID,
            note_id=ENTITY_ID,
            question="question",
        ),
        "Card",
    ),
    "note": (
        lambda: notes_db.insert_note(
            material_id=MATERIAL_ID,
            link_id=None,
            title=None,
            content="content",
            chapter="1",
            page=1,
            tags=[],
        ),
        "Note",
    ),
    "material": (
        lambda: materials_db.insert_material(
            title="title",
            authors="authors",
            pages=1,
            material_type=enums.MaterialTypesEnum.book,
            tags=None,
            link=None,
        ),
        "Material",
    ),
    "reading_log": (
        lambda: reading_log_db.insert_log_record(
            material_id=MATERIAL_ID,
            count=1,
            date=datetime.date(2026, 1, 1),
        ),
        "Reading log",
    ),
    "repeat": (
        lambda: materials_db.repeat_material(material_id=MATERIAL_ID),
        "Repeat",
    ),
}


@pytest.mark.parametrize("case", INSERTS.values(), ids=INSERTS.keys())
async def test_insert_that_affects_no_rows_raises(zero_rowcount_session, case):
    call, entity = case

    with pytest.raises(
        database.DatabaseException,
        match=f"{entity} insert affected 0 rows",
    ):
        await call()


UPDATES = {
    "note": (
        lambda note_id: notes_db.update_note(
            note_id=note_id,
            material_id=MATERIAL_ID,
            link_id=None,
            title=None,
            content="content",
            page=1,
            chapter="1",
            tags=[],
        ),
        "Note",
    ),
    "delete_note": (lambda note_id: notes_db.delete_note(note_id=note_id), "Note"),
    "restore_note": (lambda note_id: notes_db.restore_note(note_id=note_id), "Note"),
    "material": (
        lambda material_id: materials_db.update_material(
            material_id=material_id,
            title="title",
            authors="authors",
            pages=1,
            material_type=enums.MaterialTypesEnum.book,
            tags=None,
            link=None,
        ),
        "Material",
    ),
    "outline_material": (
        lambda material_id: materials_db.outline_material(material_id=material_id),
        "Material",
    ),
}


@pytest.mark.parametrize("case", UPDATES.values(), ids=UPDATES.keys())
async def test_update_that_matches_no_rows_raises_not_found(zero_rowcount_session, case):
    call, entity = case
    with pytest.raises(database.NotFoundException, match=f"{entity} id=.*not found"):
        await call(ENTITY_ID)


STATE_TRANSITIONS = {
    "start_material": (
        lambda material_id: materials_db.start_material(
            material_id=material_id,
            started_at=datetime.date(2026, 1, 1),
        ),
        "is not in the queue",
    ),
    "complete_material": (
        lambda material_id: materials_db.complete_material(
            material_id=material_id,
            completed_at=datetime.date(2026, 1, 1),
        ),
        "is not being read",
    ),
}


@pytest.mark.parametrize("case", STATE_TRANSITIONS.values(), ids=STATE_TRANSITIONS.keys())
async def test_state_transition_of_an_existing_material_that_matches_no_rows_is_conflict(
    zero_rowcount_session,
    mocker,
    case,
):
    get_material = mocker.patch.object(
        materials_db, "get_material", mocker.AsyncMock(return_value=object())
    )
    call, reason = case

    with pytest.raises(database.ConflictException, match=reason):
        await call(ENTITY_ID)
    get_material.assert_awaited_once_with(material_id=ENTITY_ID)


@pytest.mark.parametrize("case", STATE_TRANSITIONS.values(), ids=STATE_TRANSITIONS.keys())
async def test_state_transition_of_a_missing_material_is_not_found(
    zero_rowcount_session,
    mocker,
    case,
):
    mocker.patch.object(materials_db, "get_material", mocker.AsyncMock(return_value=None))
    call, _ = case

    with pytest.raises(database.NotFoundException, match="Material id=.*not found"):
        await call(ENTITY_ID)
