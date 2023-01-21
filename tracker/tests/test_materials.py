import pytest

from tracker.materials import db


@pytest.mark.asyncio
async def test_get_mean_read_pages():
    from tracker.reading_log.statistics import get_mean_read_pages

    assert await db._get_mean_read_pages() == await get_mean_read_pages()