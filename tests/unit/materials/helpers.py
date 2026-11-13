import datetime
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

import sqlalchemy.sql as sa
from sqlalchemy.dialects import postgresql

from tracker.materials import db as materials_db
from tracker.models import enums


NOW = datetime.datetime(2024, 3, 10, 12, 30, 45)
TODAY = NOW.date()


def uid(number: int) -> UUID:
    return UUID(int=number)


def day(offset: int) -> datetime.date:
    """The date `offset` days away from the frozen today."""
    return TODAY + datetime.timedelta(days=offset)


def midnight(offset: int) -> datetime.datetime:
    return datetime.datetime.combine(day(offset), datetime.time())


def compile_sql(stmt: sa.ClauseElement) -> str:
    compiled = stmt.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True},
    )
    return " ".join(str(compiled).split())


def make_material(**overrides: Any) -> materials_db.Material:
    fields: dict[str, Any] = {
        "material_id": uid(1),
        "title": "Преступление и наказание",
        "authors": "Достоевский",
        "pages": 100,
        "material_type": enums.MaterialTypesEnum.book,
        "tags": None,
        "link": None,
        "added_at": datetime.datetime(2024, 1, 1, 8, 0),
        "is_outlined": False,
        "started_at": None,
        "completed_at": None,
    }
    return materials_db.Material(**(fields | overrides))


def fake_session_factory(session: object) -> Callable[..., Any]:
    @asynccontextmanager
    async def _session(**_kwargs: Any) -> AsyncGenerator[object]:
        yield session

    return _session


class FakeResponse:
    def __init__(
        self,
        *,
        json_data: Any = None,
        text: str = "",
        raise_for_status_exc: Exception | None = None,
    ) -> None:
        self._json_data = json_data
        self._text = text
        self._raise_for_status_exc = raise_for_status_exc
        self.calls: list[str] = []
        self.text_encodings: list[str] = []

    async def json(self) -> Any:
        self.calls.append("json")
        return self._json_data

    async def text(self, encoding: str) -> str:
        self.calls.append("text")
        self.text_encodings.append(encoding)
        return self._text

    def raise_for_status(self) -> None:
        self.calls.append("raise_for_status")
        if self._raise_for_status_exc:
            raise self._raise_for_status_exc


class FakeSession:
    def __init__(self, response: FakeResponse) -> None:
        self._response = response
        self.get_calls: list[tuple[str, dict[str, Any] | None]] = []
        self.is_closed = False

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> bool:
        self.is_closed = True
        return False

    async def get(self, url: str, *, params: dict[str, Any] | None = None) -> FakeResponse:
        self.get_calls.append((url, params))
        return self._response


class FakeClientSessionFactory:
    """Stands in for `aiohttp.ClientSession` and records the timeout it was built with."""

    def __init__(self, session: FakeSession) -> None:
        self.session = session
        self.timeouts: list[Any] = []

    def __call__(self, *, timeout: Any) -> FakeSession:
        self.timeouts.append(timeout)
        return self.session
