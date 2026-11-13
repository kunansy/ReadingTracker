import logging

import pytest

from tracker.common import deprecated, deprecated_async, settings


def _warnings(caplog) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if record.name == settings.LOGGER_NAME and record.levelno == logging.WARNING
    ]


def test_deprecated_returns_result_and_passes_arguments():
    @deprecated
    def add(first: int, second: int = 0, *, third: int = 0) -> int:
        return first + second + third

    assert add(1, 2, third=3) == 6


def test_deprecated_warns_on_every_call(caplog):
    @deprecated
    def old() -> None:
        return None

    with caplog.at_level(logging.WARNING, logger=settings.LOGGER_NAME):
        old()
        old()

    assert _warnings(caplog) == ["Call to deprecated function 'old'"] * 2


def test_deprecated_does_not_warn_before_the_call(caplog):
    with caplog.at_level(logging.WARNING, logger=settings.LOGGER_NAME):

        @deprecated
        def old() -> None:
            return None

    assert _warnings(caplog) == []


def test_deprecated_keeps_metadata_of_the_function():
    @deprecated
    def old() -> None:
        """Old docstring."""

    assert old.__name__ == "old"
    assert old.__doc__ == "Old docstring."
    assert old.__wrapped__.__name__ == "old"


def test_deprecated_propagates_error_of_the_function(caplog):
    @deprecated
    def broken() -> None:
        raise ValueError("boom")

    with (
        caplog.at_level(logging.WARNING, logger=settings.LOGGER_NAME),
        pytest.raises(ValueError, match="boom"),
    ):
        broken()

    assert _warnings(caplog) == ["Call to deprecated function 'broken'"]


def test_deprecated_marks_the_wrapped_function_only_after_a_call_current_behaviour():
    @deprecated
    def old() -> None:
        return None

    assert not hasattr(old.__wrapped__, "__deprecated__")

    old()

    assert old.__wrapped__.__deprecated__ is True


@pytest.mark.xfail(
    strict=True,
    reason=(
        "BUG: tracker/common/__init__.py:12 __deprecated__ is set on the inner function "
        "at call time, the decorated function itself never carries the marker"
    ),
)
def test_deprecated_marks_the_decorated_function():
    @deprecated
    def old() -> None:
        return None

    old()

    assert old.__deprecated__ is True


async def test_deprecated_async_returns_result_and_passes_arguments():
    @deprecated_async
    async def add(first: int, second: int = 0, *, third: int = 0) -> int:
        return first + second + third

    assert await add(1, 2, third=3) == 6


async def test_deprecated_async_warns_when_called(caplog):
    @deprecated_async
    async def old() -> None:
        return None

    with caplog.at_level(logging.WARNING, logger=settings.LOGGER_NAME):
        await old()

    assert _warnings(caplog) == ["Call to deprecated function 'old'"]


async def test_deprecated_async_keeps_metadata_of_the_function():
    @deprecated_async
    async def old() -> None:
        """Old docstring."""

    assert old.__name__ == "old"
    assert old.__doc__ == "Old docstring."


async def test_deprecated_async_propagates_error_of_the_function():
    @deprecated_async
    async def broken() -> None:
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        await broken()


async def test_deprecated_async_marks_the_wrapped_function_current_behaviour():
    @deprecated_async
    async def old() -> None:
        return None

    await old()

    assert old.__wrapped__.__deprecated__ is True


@pytest.mark.xfail(
    strict=True,
    reason=(
        "BUG: tracker/common/__init__.py:24 __deprecated__ is set on the inner function "
        "at call time, the decorated coroutine function never carries the marker"
    ),
)
async def test_deprecated_async_marks_the_decorated_function():
    @deprecated_async
    async def old() -> None:
        return None

    await old()

    assert old.__deprecated__ is True
