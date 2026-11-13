from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from typing import Any



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
