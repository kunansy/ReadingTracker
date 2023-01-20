import statistics
from decimal import Decimal

import pytest
import sqlalchemy.sql as sa

from tracker.common import database
from tracker.models import models
from tracker.reading_log import db


@pytest.mark.parametrize(
    "lst,index,default,value", (
        ([], 1, -1, -1),
        ([1], 0, -1, 1),
        ([3, 4, 5], -1, -1, 5),
        ([1, 1, 1], 1, -1, 1),
    )
)
def test_safe_list_get(lst, index, default, value):
    assert db._safe_list_get(lst, index, default) == value


@pytest.mark.asyncio
async def test_get_mean_materials_read_pages():
    stat = await db.get_mean_materials_read_pages()

    stmt = sa.select([models.ReadingLog.c.material_id,
                      models.ReadingLog.c.count])

    async with database.session() as ses:
        result = (await ses.execute(stmt)).all()

    expected_stat = {}
    for material_id, count in result:
        count = Decimal(count)
        expected_stat[material_id] = expected_stat.get(material_id, []) + [count]

    expected_result = {
        material_id: round(statistics.mean(counts), 2)
        for material_id, counts in expected_stat.items()
    }

    assert expected_result == stat


@pytest.mark.asyncio
async def test_get_log_records():
    stmt = sa.select(sa.func.count(1))\
        .select_from(models.ReadingLog)

    res = await db.get_log_records()

    async with database.session() as ses:
        expected_res_count = await ses.scalar(stmt)

    assert len(res) == expected_res_count


@pytest.mark.asyncio
async def test_get_reading_material_titles():
    stmt = sa.select([models.Materials.c.material_id,
                      models.Materials.c.title]) \
        .join(models.Statuses,
              models.Statuses.c.material_id == models.Materials.c.material_id) \
        .where(models.Statuses.c.completed_at == None)

    async with database.session() as ses:
        expected = {
            str(material_id): title
            for material_id, title in (await ses.execute(stmt)).all()
        }

    titles = await db.get_reading_material_titles()

    # not null
    assert all(titles.keys())
    assert all(titles.values())
    assert expected == titles


@pytest.mark.asyncio
async def test_get_completion_dates():
    result = await db.get_completion_dates()

    stmt = sa.select([models.Materials.c.material_id,
                      models.Statuses.c.completed_at]) \
        .join(models.Statuses,
              models.Statuses.c.material_id == models.Materials.c.material_id) \
        .where(models.Statuses.c.completed_at != None)

    async with database.session() as ses:
        expected = {
            str(material_id): completed_at
            for material_id, completed_at in (await ses.execute(stmt)).all()
        }

    assert all(expected.values())
    assert expected == result
