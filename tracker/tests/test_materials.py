import uuid

import pytest
import sqlalchemy.sql as sa

from tracker.common import database
from tracker.materials import db
from tracker.models import models


@pytest.mark.asyncio
async def test_get_mean_read_pages():
    from tracker.reading_log.statistics import get_mean_read_pages

    assert await db._get_mean_read_pages() == await get_mean_read_pages()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "material_id", (
        None,
        "fd569d08-240e-4f60-b39d-e37265fbfe24"
    )
)
async def test_get_material(material_id):
    if not material_id:
        assert await db.get_material(material_id=str(uuid.uuid4())) is None
        return

    material = await db.get_material(material_id=material_id)

    stmt = sa.select(models.Materials)\
        .where(models.Materials.c.material_id == material_id)

    async with database.session() as ses:
        row = (await ses.execute(stmt)).mappings().one()
    expected = db.Material(**row)

    assert expected == material