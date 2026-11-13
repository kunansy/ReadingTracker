import logging
from collections.abc import AsyncGenerator

import httpx
import pytest

from tracker.common import settings
from tracker.main import app


@pytest.fixture
async def lenient_client() -> AsyncGenerator[httpx.AsyncClient]:
    """A client that turns an unhandled application error into the 500 a real server sends."""
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


@pytest.fixture
def tracker_log(caplog):
    caplog.set_level(logging.DEBUG, logger=settings.LOGGER_NAME)

    def records(min_level: int = logging.DEBUG) -> list[logging.LogRecord]:
        return [
            record
            for record in caplog.records
            if record.name == settings.LOGGER_NAME and record.levelno >= min_level
        ]

    return records
