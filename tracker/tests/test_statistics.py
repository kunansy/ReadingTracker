import random
import statistics
import uuid
from decimal import Decimal

import pytest
import sqlalchemy.sql as sa

from tracker.common import database
from tracker.models import models
from tracker.reading_log import statistics as st, db


@pytest.mark.asyncio
async def test_get_m_log_statistics():
    pass


@pytest.mark.asyncio
async def test_get_start_date():
    records = await db.get_log_records()
    start_date = await st._get_start_date()

    assert min(records, key=lambda record: record.date).date == start_date


@pytest.mark.asyncio
async def test_get_last_date():
    records = await db.get_log_records()
    last_date = await st._get_last_date()

    assert max(records, key=lambda record: record.date).date == last_date


@pytest.mark.asyncio
async def test_get_log_duration():
    duration = await st._get_log_duration()
    records = await db.get_log_records()

    expected_duration = (max(records, key=lambda record: record.date).date -
                         min(records, key=lambda record: record.date).date).days + 1

    assert duration == expected_duration


@pytest.mark.asyncio
async def test_get_total_read_pages():
    total = await st._get_total_read_pages()
    records = await db.get_log_records()

    assert total == sum(record.count for record in records)


@pytest.mark.asyncio
async def test_get_lost_days():
    lost_days = await st._get_lost_days()
    records = await db.get_log_records()

    expected_duration = (max(records, key=lambda record: record.date).date -
                         min(records, key=lambda record: record.date).date).days + 1

    assert lost_days == expected_duration - len(records)


@pytest.mark.asyncio
async def test_get_mean_read_pages():
    mean = await st.get_mean_read_pages()
    records = await db.get_log_records()

    expected_mean = statistics.mean(Decimal(record.count) for record in records)
    assert mean == round(expected_mean, 2)


@pytest.mark.asyncio
async def test_get_median_pages_read_per_day():
    median = await st._get_median_pages_read_per_day()
    records = await db.get_log_records()

    expected_median = statistics.median(record.count for record in records)

    assert median == expected_median


@pytest.mark.asyncio
async def test_contains():
    records = await db.get_log_records()

    assert all([
        await st.contains(material_id=record.material_id)
        for record in random.sample(records, 10)
    ])

    assert not await st.contains(material_id=str(uuid.uuid4()))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'material_id', (
        "5c66e1ca-eb52-47e5-af50-c48b345c7e6c",
        None,
    )
)
async def test_get_min_record(material_id):
    min_record = await st._get_min_record(material_id=material_id)
    records = await db.get_log_records()
    if material_id:
        records = [
            record for record in records
            if record.material_id == material_id
        ]

    expected = min(records, key=lambda record: record.count)

    assert min_record.material_id == expected.material_id
    assert min_record.count == expected.count
    assert min_record.date == expected.date


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'material_id', (
        "5c66e1ca-eb52-47e5-af50-c48b345c7e6c",
        None,
    )
)
async def test_get_max_record(material_id):
    max_record = await st._get_max_record(material_id=material_id)
    records = await db.get_log_records()
    if material_id:
        records = [
            record for record in records
            if record.material_id == material_id
        ]

    expected = max(records, key=lambda record: record.count)

    assert max_record.material_id == expected.material_id
    assert max_record.count == expected.count
    assert max_record.date == expected.date


@pytest.mark.asyncio
async def test_get_min_record_nof_found():
    result = await st._get_min_record(material_id=str(uuid.uuid4()))
    assert result is None


@pytest.mark.asyncio
async def test_get_max_record_nof_found():
    result = await st._get_max_record(material_id=str(uuid.uuid4()))
    assert result is None


@pytest.mark.asyncio
async def test_would_be_total():
    would_be_total = await st._would_be_total()
    records = await db.get_log_records()

    counts = [record.count for record in records]
    duration = (max(records, key=lambda record: record.date).date -
                min(records, key=lambda record: record.date).date).days + 1

    expected = sum(counts)
    expected += statistics.mean(counts) * (duration - len(records))

    assert would_be_total == round(expected)


@pytest.mark.asyncio
async def test_get_total_materials_completed():
    materials = await st._get_total_materials_completed()

    stmt = sa.select(sa.func.count(1))\
        .where(models.Statuses.c.completed_at != None)

    async with database.session() as ses:
        expected = await ses.scalar(stmt)

    assert materials == expected


@pytest.mark.asyncio
async def test_get_tracker_statistics():
    stat = await st.get_tracker_statistics()

    assert stat
    assert stat.lost_time_percent == round(stat.lost_time / stat.duration, 2) * 100
    assert stat.would_be_total_percent == round(stat.would_be_total / stat.total_pages_read, 2) * 100

    stat.duration = 701
    assert stat.duration_period == "1 years 11 months 11 days"
    stat.lost_time = 701
    assert stat.lost_time_period == "1 years 11 months 11 days"

    stat.lost_time = 23
    stat.duration = 100
    assert stat.lost_time_percent == 23.

    stat.would_be_total = 142
    stat.total_pages_read = 71
    assert stat.would_be_total_percent == 200.
