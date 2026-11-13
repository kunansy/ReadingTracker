import datetime
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from typing import Any, NamedTuple

import httpx
import pytest

from tests.unit.helpers import NOW
from tracker.common import database
from tracker.main import app


class RealDatabaseApi(NamedTuple):
    session: Callable[..., Any]
    transaction: Callable[..., Any]


_REAL_DATABASE_API = RealDatabaseApi(
    session=database.session,
    transaction=database.transaction,
)


@asynccontextmanager
async def _forbidden_session(**_kwargs) -> AsyncGenerator[None]:
    raise AssertionError(
        "A unit test opened a database session. Mock the db function, "
        "or move the test to tests/integration.",
    )
    yield


@pytest.fixture(autouse=True)
def forbid_database(monkeypatch):
    monkeypatch.setattr(database, "session", _forbidden_session)
    monkeypatch.setattr(database, "transaction", _forbidden_session)


@pytest.fixture
def real_database_api() -> RealDatabaseApi:
    """The unpatched session()/transaction(), for tests of those two functions."""
    return _REAL_DATABASE_API


@pytest.fixture
async def client() -> AsyncGenerator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


@pytest.fixture
def dependency_overrides():
    yield app.dependency_overrides
    app.dependency_overrides.clear()


@pytest.fixture
def frozen_now(mocker) -> datetime.datetime:
    mocker.patch.object(database, "utcnow", return_value=NOW)
    return NOW
