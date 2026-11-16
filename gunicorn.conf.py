import functools
import os
import signal

from gunicorn.arbiter import Arbiter
from gunicorn.workers.base import Worker

from tracker.common import (
    database,
    workers as tracker_workers,
)


def on_starting(server: Arbiter) -> None:  # noqa: ARG001
    """Migrate the database once in the master, before workers are forked."""
    database.migrate_db()


def post_fork(server: Arbiter, worker: Worker) -> None:  # noqa: ARG001
    """Let a worker ask the master to restart every worker, e.g. after a restore."""
    tracker_workers.set_reloader(functools.partial(os.kill, server.pid, signal.SIGHUP))
