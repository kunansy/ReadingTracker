import functools
from collections.abc import Callable, Coroutine
from typing import Any

from tracker.common.logger import logger


def deprecated[T](func: Callable[[Any], T]) -> Callable[[Any], T]:
    @functools.wraps(func)
    def wrapped(*args: Any, **kwargs) -> T:
        logger.warning("Call to deprecated function '%s'", func.__name__)
        setattr(func, "__deprecated__", True)
        return func(*args, **kwargs)

    return wrapped


def deprecated_async[T](
    func: Callable[[Any], Coroutine[Any, Any, T]],
) -> Callable[[Any], Coroutine[Any, Any, T]]:
    @functools.wraps(func)
    async def wrapped(*args: Any, **kwargs) -> T:
        logger.warning("Call to deprecated function '%s'", func.__name__)
        setattr(func, "__deprecated__", True)
        return await func(*args, **kwargs)

    return wrapped
