import uuid

import pytest
import sqlalchemy.sql as sa

from tracker.common import database
from tracker.materials import db
from tracker.models import models


async def get_materials() -> list[db.Material]:
    stmt = sa.select(models.Materials)

    async with database.session() as ses:
        return [
            db.Material(**row)
            for row in (await ses.execute(stmt)).mappings().all()
        ]


async def get_statuses() -> list[db.Status]:
    stmt = sa.select(models.Statuses)

    async with database.session() as ses:
        return [
            db.Status(**row)
            for row in (await ses.execute(stmt)).mappings().all()
        ]


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


@pytest.mark.asyncio
async def test_get_free_materials():
    free_materials = await db._get_free_materials()

    materials = await get_materials()
    statuses = await get_statuses()
    status_ids = {status.material_id for status in statuses}

    expected_free_materials = {
        material.material_id
        for material in materials
        if material.material_id not in status_ids
    }

    assert len(free_materials) == len(expected_free_materials)
    assert all(
        material.material_id in expected_free_materials
        for material in free_materials
    )


def test_get_reading_materials_stmt():
    stmt = db._get_reading_materials_stmt()

    assert isinstance(stmt, sa.Select)