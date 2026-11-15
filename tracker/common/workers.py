from collections.abc import Callable

from tracker.common.logger import logger


type WorkersReloader = Callable[[], None]

# Registered by the gunicorn post_fork hook; absent in the CLI and in tests.
_reloader: WorkersReloader | None = None


def set_reloader(reloader: WorkersReloader) -> None:
    global _reloader  # noqa: PLW0603
    _reloader = reloader


def reload_workers() -> bool:
    if _reloader is None:
        logger.warning("No workers reloader is registered, restart tracker-app manually")
        return False

    _reloader()
    return True
