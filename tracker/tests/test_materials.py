import datetime
import random
import uuid
from typing import Literal

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


def test_get_completed_materials_stmt():
    stmt = db._get_completed_materials_stmt()

    assert isinstance(stmt, sa.Select)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "is_completed", (
        True, False
    )
)
async def test_parse_material_status_response(is_completed):
    if is_completed:
        stmt = db._get_completed_materials_stmt()
    else:
        stmt = db._get_reading_materials_stmt()

    result = await db._parse_material_status_response(stmt=stmt)
    assert result


@pytest.mark.asyncio
async def test_get_reading_materials():
    reading_materials = await db._get_reading_materials()

    materials = {
        material.material_id: material
        for material in await get_materials()
    }
    statuses = {
        status.material_id: status
        for status in await get_statuses()
    }

    expected = {
        material_id
        for material_id in materials
        if material_id in statuses and not statuses[material_id].completed_at
    }

    assert len(reading_materials) == len(expected)
    assert all(
        material.material_id in expected
        for material in reading_materials
    )

    assert all(
        material.material == materials[material.material_id]
        for material in reading_materials
    )
    assert all(
        material.status == statuses[material.material_id]
        for material in reading_materials
    )


@pytest.mark.asyncio
async def test_get_completed_materials():
    completed_materials = await db._get_completed_materials()

    materials = {
        material.material_id: material
        for material in await get_materials()
    }
    statuses = {
        status.material_id: status
        for status in await get_statuses()
    }

    expected = {
        material_id
        for material_id in materials
        if material_id in statuses and statuses[material_id].completed_at
    }

    assert len(completed_materials) == len(expected)
    assert all(
        material.material_id in expected
        for material in completed_materials
    )

    assert all(
        material.material == materials[material.material_id]
        for material in completed_materials
    )
    assert all(
        material.status == statuses[material.material_id]
        for material in completed_materials
    )


@pytest.mark.asyncio
async def test_get_last_material_started():
    material_id = await db.get_last_material_started()

    stmt = sa.select(models.Materials.c.material_id)\
        .join(models.Statuses,
              models.Statuses.c.material_id == models.Materials.c.material_id)\
        .where(models.Statuses.c.completed_at == None)\
        .order_by(models.Statuses.c.started_at.desc())\
        .limit(1)

    async with database.session() as ses:
        expected = await ses.scalar(stmt)

    assert expected == material_id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "material_status", (
        "completed", "started", "not started"
    )
)
async def test_get_status(material_status: Literal["completed", "started", "not started"]):
    materials = {
        material.material_id: material
        for material in await get_materials()
    }
    statuses = {
        status.material_id: status
        for status in await get_statuses()
    }

    if material_status == "not started":
        material_id = random.choice([
            material_id for material_id in materials
            if material_id not in statuses
        ])
    elif material_status == "completed":
        material_id = random.choice([
            material_id for material_id in materials
            if material_id in statuses and statuses[material_id].completed_at
        ])
    elif material_status == "started":
        material_id = random.choice([
            material_id for material_id in materials
            if material_id in statuses and not statuses[material_id].completed_at
        ])

    status = await db._get_status(material_id=material_id)
    assert status == statuses.get(material_id)


@pytest.mark.parametrize(
    "duration,expected", (
        (365, "1 years"),
        (1, "1 days"),
        (30, "1 months"),
        (31, "1 months 1 days"),
        (65, "2 months 5 days"),
        (395, "1 years 1 months"),
        (790, "2 years 2 months"),
        (380, "1 years 15 days"),
        (792, "2 years 2 months 2 days"),
        (datetime.timedelta(days=792), "2 years 2 months 2 days"),
    )
)
def test_convert_duration_to_period(duration, expected):
    assert db._convert_duration_to_period(duration) == expected
