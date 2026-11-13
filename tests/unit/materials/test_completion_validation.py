from types import SimpleNamespace

import pytest

from tests.unit.materials.helpers import day, make_material, midnight, uid
from tracker.common import database
from tracker.materials import db
from tracker.reading_log import db as log_db


MATERIAL_ID = uid(1)


def _logs(*counts: int) -> list[log_db.LogRecord]:
    return [
        log_db.LogRecord(material_id=MATERIAL_ID, count=count, date=day(-index))
        for index, count in enumerate(counts)
    ]


@pytest.fixture
def lookups(mocker, frozen_now):
    return SimpleNamespace(
        get_material=mocker.patch.object(
            db,
            "get_material",
            mocker.AsyncMock(
                return_value=make_material(pages=100, started_at=midnight(-5)),
            ),
        ),
        list_log_records=mocker.patch.object(
            log_db,
            "list_log_records",
            mocker.AsyncMock(return_value=_logs(60, 40)),
        ),
    )


@pytest.mark.parametrize(
    "completed_at",
    [None, day(0), day(-1), day(-5)],
    ids=["default-today", "today", "yesterday", "on-the-start-day"],
)
async def test_fully_read_material_can_be_completed(lookups, completed_at):
    await db.is_completion_request_valid(
        material_id=MATERIAL_ID,
        completed_at=completed_at,
    )

    lookups.get_material.assert_awaited_once_with(material_id=MATERIAL_ID)
    lookups.list_log_records.assert_awaited_once_with(material_id=MATERIAL_ID)


async def test_material_started_later_today_can_be_completed_today(lookups):
    lookups.get_material.return_value = make_material(
        pages=100,
        started_at=midnight(0).replace(hour=23, minute=59),
    )

    await db.is_completion_request_valid(material_id=MATERIAL_ID, completed_at=day(0))


async def test_missing_material_raises_not_found(lookups):
    lookups.get_material.return_value = None

    with pytest.raises(database.NotFoundException, match="Material id=.* not found"):
        await db.is_completion_request_valid(material_id=MATERIAL_ID)


async def test_not_started_material_is_rejected(lookups):
    lookups.get_material.return_value = make_material(started_at=None)

    with pytest.raises(ValueError, match="^Material is not started$"):
        await db.is_completion_request_valid(material_id=MATERIAL_ID)


async def test_already_completed_material_is_rejected(lookups):
    lookups.get_material.return_value = make_material(
        started_at=midnight(-5),
        completed_at=midnight(-1),
    )

    with pytest.raises(ValueError, match="^Material is already completed$"):
        await db.is_completion_request_valid(material_id=MATERIAL_ID)


@pytest.mark.parametrize("offset", [1, 365], ids=["tomorrow", "next-year"])
async def test_completion_in_the_future_is_rejected(lookups, offset):
    with pytest.raises(ValueError, match="^Completion date must not be in the future$"):
        await db.is_completion_request_valid(
            material_id=MATERIAL_ID,
            completed_at=day(offset),
        )


async def test_completion_before_the_start_is_rejected(lookups):
    with pytest.raises(ValueError, match="^Completion date must not be before the start date$"):
        await db.is_completion_request_valid(
            material_id=MATERIAL_ID,
            completed_at=day(-6),
        )


async def test_material_without_reading_logs_is_rejected(lookups):
    lookups.list_log_records.return_value = []

    with pytest.raises(ValueError, match="^Reading logs not found$"):
        await db.is_completion_request_valid(material_id=MATERIAL_ID)


@pytest.mark.parametrize("counts", [(60, 39), (60, 41), (1,)], ids=["one-less", "one-more", "few"])
async def test_material_with_unread_or_extra_pages_is_rejected(lookups, counts):
    lookups.list_log_records.return_value = _logs(*counts)

    with pytest.raises(ValueError, match="^Invalid pages count, something is unread$"):
        await db.is_completion_request_valid(material_id=MATERIAL_ID)


async def test_state_errors_take_precedence_over_date_errors(lookups):
    lookups.get_material.return_value = make_material(started_at=None)

    with pytest.raises(ValueError, match="^Material is not started$"):
        await db.is_completion_request_valid(
            material_id=MATERIAL_ID,
            completed_at=day(10),
        )
