from gunicorn.arbiter import Arbiter

from tracker.common import database


def on_starting(server: Arbiter) -> None:  # noqa: ARG001
    """Migrate the database once in the master, before workers are forked."""
    database.migrate_db()
