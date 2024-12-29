import random
from collections.abc import Sequence
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import sqlalchemy.sql as sa

from tracker.common import database
from tracker.materials import db as materials_db
from tracker.models import models
from tracker.reading_log import (
    db,
    statistics as st,
)


def mean(coll: Sequence[int | float | Decimal]) -> int | float | Decimal:
    return sum(coll) / len(coll)


@pytest.mark.parametrize(
    "material_id",
    [
        # clear reading, Foer
        UUID("5c66e1ca-eb52-47e5-af50-c48b345c7e6c"),
        # 451, Bradbury, some material inside completed, some read
        UUID("a4fec52b-ed43-48e8-a888-d393606ac010"),
        # Lermontov
        UUID("dd89c273-3bbe-49f8-8049-239379a7fc65"),
        # Bulgakov
        UUID("fd569d08-240e-4f60-b39d-e37265fbfe24"),
    ],
)
async def test_calculate_materials_stat(material_id):
    records = await db.get_log_records()

    stats = await st.calculate_materials_stat({material_id})
    stat = stats[material_id]

    material_records = [record for record in records if record.material_id == material_id]
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


async def test_get_start_date():
    records = await db.get_log_records()
    start_date = await st._get_start_date()

    assert min(records, key=lambda record: record.date).date == start_date


async def test_get_last_date():
    records = await db.get_log_records()
    last_date = await st._get_last_date()

    assert max(records, key=lambda record: record.date).date == last_date


async def test_get_log_duration():
    duration = await st._get_log_duration()
    records = await db.get_log_records()

    expected_duration = (
        max(records, key=lambda record: record.date).date
        - min(records, key=lambda record: record.date).date
    ).days + 1

    assert duration == expected_duration


async def test_get_total_read_pages():
    total = await st._get_total_read_pages()
    records = await db.get_log_records()

    assert total == sum(record.count for record in records)


async def test_get_lost_days():
    lost_days = await st._get_lost_days()
    _dt = models.ReadingLog.c.date
    expected_duration_stmt = sa.select(
        sa.func.max(_dt) - sa.func.min(_dt) + 1
    )
    filled_days_count_stmt = sa.select(sa.func.count(_dt.distinct()))

    async with database.session() as ses:
        expected_duration = await ses.scalar(expected_duration_stmt)
        filled_days_count = await ses.scalar(filled_days_count_stmt)

    assert lost_days == expected_duration - filled_days_count


async def test_get_means():
    means = await st.get_means()
    records = await db.get_log_records()

    assert records

    materials = {
        material.material_id: material.material_type
        for material in await materials_db.get_materials()
    }
    material_to_date = {
        material_type: {record.date: 0 for record in records}
        for material_type in materials.values()
    }
    for record in records:
        material_type = materials[record.material_id]
        material_to_date[material_type][record.date] += record.count

    expected = {
        material_type: mean([Decimal(value) for value in dates.values() if value != 0])
        for material_type, dates in material_to_date.items()
    }

    for material_type, mean_ in means.items():
        assert round(expected[material_type], 2) == mean_


async def test_get_median_pages_read_per_day():
    median = await st._get_median_pages_read_per_day()
    records = await db.get_log_records()

    counts = sorted(record.count for record in records)
    if (length := len(counts)) % 2:
        expected_median = counts[length // 2]
    else:
        expected_median = (counts[length // 2 - 1] + counts[length // 2]) / 2

    assert median == expected_median


async def test_contains():
    records = await db.get_log_records()

    assert all(
        [
            await st.contains(material_id=record.material_id)
            for record in random.sample(records, 10)
        ],
    )

    assert not await st.contains(material_id=uuid4())


@pytest.mark.parametrize(
    "material_id",
    [
        UUID("5c66e1ca-eb52-47e5-af50-c48b345c7e6c"),
        None,
    ],
)
async def test_get_min_record(material_id):
    min_record = await st._get_min_record(material_id=material_id)
    records = await db.get_log_records()
    if material_id:
        records = [record for record in records if record.material_id == material_id]

    expected = min(records, key=lambda record: record.count)

    assert min_record.material_id == expected.material_id
    assert min_record.count == expected.count
    assert min_record.date == expected.date


@pytest.mark.parametrize(
    "material_id",
    [
        UUID("5c66e1ca-eb52-47e5-af50-c48b345c7e6c"),
        None,
    ],
)
async def test_get_max_record(material_id):
    max_record = await st._get_max_record(material_id=material_id)
    records = await db.get_log_records()
    if material_id:
        records = [record for record in records if record.material_id == material_id]

    expected = max(records, key=lambda record: record.count)

    assert max_record.material_id == expected.material_id
    assert max_record.count == expected.count
    assert max_record.date == expected.date


async def test_get_min_record_nof_found():
    result = await st._get_min_record(material_id=uuid4())
    assert result is None


async def test_get_max_record_nof_found():
    result = await st._get_max_record(material_id=uuid4())
    assert result is None


async def test_would_be_total():
    mean_dict = await st.get_means()
    total_pages = await st._get_total_read_pages()
    lost_time = await st._get_lost_days()

    would_be_total = st._would_be_total(
        means=mean_dict,
        total_read_pages=total_pages,
        lost_time=lost_time
    )

    overall_mean = round(sum(mean_dict.values()) / len(mean_dict))
    expected = total_pages + overall_mean * lost_time

    assert would_be_total == expected
    # TODO: check percent relation


async def test_get_total_materials_completed():
    materials = await st._get_total_materials_completed()

    stmt = sa.select(sa.func.count(1)).where(models.Statuses.c.completed_at != None)

    async with database.session() as ses:
        expected = await ses.scalar(stmt)

    assert materials == expected


async def test_get_tracker_statistics():
    stat = await st.get_tracker_statistics()

    assert stat
    assert stat.lost_time_percent == round(stat.lost_time / stat.duration * 100, 2)
    assert (
        stat.would_be_total_percent
        == round(stat.would_be_total / stat.total_pages_read, 2) * 100
    )

    stat.duration = 706
    assert stat.duration_period == "1 years, 11 months, 11 days"
    stat.lost_time = 706
    assert stat.lost_time_period == "1 years, 11 months, 11 days"

    stat.lost_time = 23
    stat.duration = 100
    assert stat.lost_time_percent == 23

    stat.would_be_total = 142
    stat.total_pages_read = 71
    assert stat.would_be_total_percent == 200.0
