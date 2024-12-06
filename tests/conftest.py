import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.common import database


@pytest.fixture(scope="session")
def event_loop(request):
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@asynccontextmanager
async def mock_trans(**kwargs) -> AsyncGenerator[AsyncSession, None]:
    new_session = AsyncSession(**kwargs, bind=database.engine)

    try:
        async with new_session.begin() as t:
            yield new_session
            await t.rollback()
    finally:
        await new_session.close()
