import pytest
import sqlalchemy.sql as sa

from tracker.common import database


@pytest.mark.asyncio
async def test_session():
    stmt = sa.text('SELECT 1 + 1')

    async with database.session() as ses:
        assert await ses.scalar(stmt) == 2


@pytest.mark.asyncio
async def test_session_error():
    stmt = sa.text('SELECT 1 / 0')

    with pytest.raises(database.DatabaseException) as e:
        async with database.session() as ses:
            await ses.scalar(stmt)

    assert "division by zero" in str(e.value)
