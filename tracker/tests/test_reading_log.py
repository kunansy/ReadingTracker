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
