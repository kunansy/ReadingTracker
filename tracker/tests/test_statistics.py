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
