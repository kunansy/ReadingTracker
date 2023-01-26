import base64

import pytest

from tracker.materials import db as materials_db
from tracker.reading_log import db as logs_db, statistics
from tracker.system import db


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "material_id,last_days", (
        # clear reading, no materials inside
        ('a8297f04-6ded-459c-ae79-98c6a20e18c5', 7),
        ('a8297f04-6ded-459c-ae79-98c6a20e18c5', 14),
        ('236d5724-c0c6-431c-a3d1-a54e59dfd520', 14),
        ('533c3a90-2593-4d9a-8016-108a7b89f8ee', 14),
    )
)
async def test_get_graphic_data_clear_reading(material_id, last_days):
    result = await db._get_graphic_data(material_id=material_id, last_days=last_days)
    logs = await logs_db.get_log_records()

    material_logs = [log for log in logs if log.material_id == material_id]
    material_logs = material_logs[:last_days]
    logs_count = [log.count for log in material_logs]

    assert isinstance(result, db.ReadingData)
    assert len(result.counts) == len(material_logs)
    assert len(result.dates) == len(material_logs)

    assert result.dates == [log.date for log in material_logs]
    assert result.counts == [sum(logs_count[:elem]) for elem in range(1, len(logs_count) + 1)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "material_id,last_days", (
        # not clear reading, there are materials inside
        ('a4fec52b-ed43-48e8-a888-d393606ac010', 80),
    )
)
async def test_get_graphic_data_unclear_reading(material_id, last_days):
    result = await db._get_graphic_data(material_id=material_id, last_days=last_days)
    logs = await logs_db.get_log_records()

    material_logs = [log for log in logs if log.material_id == material_id]
    material_logs = material_logs[:last_days]
    logs_count = [log.count for log in material_logs]

    assert isinstance(result, db.ReadingData)
    assert len(result.counts) > len(material_logs)
    assert len(result.dates) > len(material_logs)

    assert set(result.counts) == {sum(logs_count[:elem]) for elem in range(1, len(logs_count) + 1)}


@pytest.mark.asyncio
async def test_get_read_material_titles():
    result = await db.get_read_material_titles()
    materials = await materials_db._get_reading_materials() + await materials_db._get_completed_materials()

    assert len(result) == len(materials)

    assert result == {
        material.material_id: material.material.title
        for material in materials
    }


@pytest.mark.asyncio
async def test_get_material_reading_now():
    assert await db.get_material_reading_now() == await logs_db.get_material_reading_now()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "material_id,last_days", (
        # completed material
        ("a8297f04-6ded-459c-ae79-98c6a20e18c5", 14),
        # not completed material
        ("a7f4e1dc-9274-46e7-a656-514bf1f312b5", 14),
    )
)
async def test_create_reading_graphic(material_id, last_days):

    result = await db.create_reading_graphic(
        material_id=material_id, last_days=last_days)

    assert result
    assert base64.b64decode(result, validate=True)


@pytest.mark.asyncio
async def test_create_reading_graphic_material_not_found():
    material_id = "d012fba9-efe0-4171-b3e7-730c3c3b2666"
    last_days = 14

    with pytest.raises(ValueError) as e:
        await db.create_reading_graphic(
            material_id=material_id, last_days=last_days)

    assert str(e.value) == "'material_id='d012fba9-efe0-4171-b3e7-730c3c3b2666'' not found"


@pytest.mark.asyncio
async def test_get_tracker_statistics():
    assert await db.get_tracker_statistics() == await statistics.get_tracker_statistics()
