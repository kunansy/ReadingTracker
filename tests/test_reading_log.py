import datetime
import random
import statistics
from decimal import Decimal

import pytest
import sqlalchemy.sql as sa

from tracker.common import database
from tracker.models import models
from tracker.reading_log import db
from tests.material_factory import complete_material, insert_material, start_material


@pytest.mark.parametrize(
    ("lst", "index", "default", "value"),
    [
        ([], 1, -1, -1),
        ([1], 0, -1, 1),
        ([3, 4, 5], -1, -1, 5),
        ([1, 1, 1], 1, -1, 1),
    ],
)
def test_safe_list_get(lst, index, default, value):
    assert db._safe_list_get(lst, index, default) == value


async def test_get_log_records():
    stmt = sa.select(sa.func.count(1)).select_from(models.ReadingLog)

    log_records = await db.list_log_records()

    async with database.session() as ses:
        expected_res_count = await ses.scalar(stmt)

    assert len(log_records) == expected_res_count


async def test_get_reading_material_titles():
    stmt = (
        sa.select(models.Materials.c.material_id, models.Materials.c.title)
        .where(models.Materials.c.started_at != None)
        .where(models.Materials.c.completed_at == None)
    )

    async with database.session() as ses:
        expected = dict((await ses.execute(stmt)).all())

    titles = await db.get_reading_material_titles()

    # not null
    assert all(titles.keys())
    assert all(titles.values())
    assert expected == titles


async def test_get_completion_dates():
    dates = await db.get_completion_dates()

    stmt = (
        sa.select(models.Materials.c.material_id, models.Materials.c.completed_at)
        .where(models.Materials.c.completed_at != None)
    )

    async with database.session() as ses:
        expected = dict((await ses.execute(stmt)).all())

    assert expected == dates
    assert all(expected.values())


async def test_is_log_empty():
    is_empty = await db.is_log_empty()

    stmt = sa.select(sa.func.count(1) == 0).select_from(models.ReadingLog)

    async with database.session() as ses:
        expected = await ses.scalar(stmt)

    assert is_empty is expected


async def test_insert_log_record():
    reading_materials = list((await db.get_reading_material_titles()).keys())

    material_id = random.choice(reading_materials)
    count = random.randint(1485, 1490)
    date = (database.utcnow() + datetime.timedelta(days=random.randint(10, 100))).date()

    await db.insert_log_record(material_id=material_id, count=count, date=date)

    stmt = (
        sa.select(models.ReadingLog)
        .where(models.ReadingLog.c.count == count)
        .where(models.ReadingLog.c.date == date)
        .where(models.ReadingLog.c.material_id == material_id)
    )

    async with database.session() as ses:
        log = (await ses.execute(stmt)).mappings().one_or_none()

    assert log
    assert log.count == count
    assert log.date == date
    assert log.material_id == material_id

    del_stmt = models.ReadingLog.delete().where(models.ReadingLog.c.log_id == log.log_id)

    async with database.session() as ses:
        await ses.execute(del_stmt)

        assert not (await ses.execute(stmt)).one_or_none()


async def test_get_completion_dates_includes_only_completed(shared_session):
    reading_id, _ = await start_material()
    completed_id, completed_at = await complete_material()

    dates = await db.get_completion_dates()

    assert reading_id not in dates
    assert dates[completed_id].date() == completed_at


@pytest.mark.parametrize("state", ["queued", "completed"])
async def test_check_record_correct_rejects_not_reading_material(shared_session, state):
    if state == "queued":
        material_id = await insert_material()
    else:
        material_id, _ = await complete_material()

    with pytest.raises(ValueError, match="No reading material"):
        await db.check_record_correct(
            material_id=material_id,
            date=database.utcnow().date(),
            count=1,
        )


async def test_check_record_correct_rejects_date_before_start(shared_session):
    material_id, started_at = await start_material()

    with pytest.raises(ValueError, match="is before the material start"):
        await db.check_record_correct(
            material_id=material_id,
            date=started_at - datetime.timedelta(days=1),
            count=1,
        )


async def test_check_record_correct_accepts_reading_material(shared_session):
    material_id, started_at = await start_material()

    await db.check_record_correct(material_id=material_id, date=started_at, count=1)
