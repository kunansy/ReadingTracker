"""Revision modules and a rolled-back migration context for the migration tests."""

import importlib.util
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy.engine import Connection

from tracker.common import database


VERSIONS = Path(__file__).resolve().parents[3] / "migrations/alembic/versions"


def load(filename: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        filename.removesuffix(".py"),
        VERSIONS / filename,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


REVISION_0001 = load("0001_baseline.py")
REVISION_0002 = load("0002_sort_key.py")
REVISION_0003 = load("0003_chapter_length.py")
REVISION_0004 = load("0004_material_status_columns.py")
REVISION_0005 = load("0005_drop_statuses.py")
REVISION_0006 = load("0006_materials_completed_at_index.py")
REVISION_0007 = load("0007_drop_materials_index.py")
ALL_REVISIONS = (
    REVISION_0001,
    REVISION_0002,
    REVISION_0003,
    REVISION_0004,
    REVISION_0005,
    REVISION_0006,
    REVISION_0007,
)


def downgrade_to(revision: ModuleType) -> None:
    """Run the downgrades from head down to `revision`, inside the current context."""
    for later in reversed(ALL_REVISIONS):
        if later is revision:
            return
        later.downgrade()


async def in_rolled_back_migration[T](check: Callable[[Connection], T]) -> T:
    """Run migration operations in a transaction that is always rolled back.

    PostgreSQL DDL is transactional, so the database stays at head even if `check` fails.
    """
    async with database.engine.connect() as conn:
        trans = await conn.begin()
        try:

            def run(sync_conn: Connection) -> T:
                with Operations.context(MigrationContext.configure(sync_conn)):
                    return check(sync_conn)

            return await conn.run_sync(run)
        finally:
            await trans.rollback()
