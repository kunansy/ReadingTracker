import pytest
import sqlalchemy.sql as sa

from tracker.common import database


@pytest.mark.asyncio
async def test_session():
    stmt = sa.text('SELECT 1 + 1')

    async with database.session() as ses:
        assert await ses.scalar(stmt) == 2
