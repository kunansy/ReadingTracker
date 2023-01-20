import random
import statistics
import uuid
from decimal import Decimal

import pytest

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
async def test_get_min_record():
    min_record = await st._get_min_record()
    records = await db.get_log_records()

    expected = min(records, key=lambda record: record.count)

    assert min_record.material_id == expected.material_id
    assert min_record.count == expected.count
    assert min_record.date == expected.date


@pytest.mark.asyncio
async def test_get_max_record():
    max_record = await st._get_max_record()
    records = await db.get_log_records()

    expected = max(records, key=lambda record: record.count)

    assert max_record.material_id == expected.material_id
    assert max_record.count == expected.count
    assert max_record.date == expected.date
