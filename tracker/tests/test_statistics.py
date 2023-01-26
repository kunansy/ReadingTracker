import random
import uuid
from decimal import Decimal
from typing import Sequence

import pytest
import sqlalchemy.sql as sa

from tracker.common import database
from tracker.models import models
from tracker.reading_log import statistics as st, db


def mean(coll: Sequence[int | float | Decimal]) -> int | float | Decimal:
    return sum(coll) / len(coll)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'material_id,logs,completion_dates', (
        ("5c66e1ca-eb52-47e5-af50-c48b345c7e6c", True, True), # clear reading, Foer
        ("5c66e1ca-eb52-47e5-af50-c48b345c7e6c", True, False),
        ("5c66e1ca-eb52-47e5-af50-c48b345c7e6c", False, True),
        ("5c66e1ca-eb52-47e5-af50-c48b345c7e6c", False, False),

        # 451, Bradbury, some material inside completed, some read
        ("a4fec52b-ed43-48e8-a888-d393606ac010", False, False),
        # Lermontov
        ("dd89c273-3bbe-49f8-8049-239379a7fc65", False, False),
        # Bulgakov
        ("fd569d08-240e-4f60-b39d-e37265fbfe24", False, False),
    )
)
async def test_get_m_log_statistics(material_id, logs, completion_dates):
    records = await db.get_log_records()
    dates = await db.get_completion_dates()

    stat = await st.get_m_log_statistics(
        material_id=material_id,
        logs=records if logs else None,
        completion_dates=dates if completion_dates else None)

    material_records = [
        record for record in records
        if record.material_id == material_id
    ]
    records_count = [record.count for record in material_records]

    assert stat
    assert stat.material_id == material_id
    assert stat.total == sum(r.count for r in material_records)
    # TODO: the field is more complex to test
    # assert stat.lost_time == duration_time - len(material_records)
    assert stat.duration == len(material_records)
    assert stat.mean == round(mean(records_count))
    assert stat.min_record.count == min(records_count)
    assert stat.max_record.count == max(records_count)


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
    mean_pages = await st.get_mean_read_pages()
    records = await db.get_log_records()
    record_counts = [Decimal(record.count) for record in records]

    assert records
    assert mean_pages == round(mean(record_counts), 2)


@pytest.mark.asyncio
async def test_get_median_pages_read_per_day():
    median = await st._get_median_pages_read_per_day()
    records = await db.get_log_records()

    counts = sorted(record.count for record in records)
    if (length := len(counts)) % 2:
        expected_median = counts[length // 2]
    else:
        expected_median = (counts[length // 2 - 1] + counts[length // 2 + 1]) / 2

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
    expected += mean(counts) * (duration - len(records))

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

    stat.duration = 706
    assert stat.duration_period == "1 years 11 months 11 days"
    stat.lost_time = 706
    assert stat.lost_time_period == "1 years 11 months 11 days"

    stat.lost_time = 23
    stat.duration = 100
    assert stat.lost_time_percent == 23.

    stat.would_be_total = 142
    stat.total_pages_read = 71
    assert stat.would_be_total_percent == 200.
