import importlib.util
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy.engine import Connection

from tracker.common import database


VERSIONS = Path(__file__).parents[1] / "migrations/alembic/versions"


def _load_migration(filename: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(filename, VERSIONS / filename)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MIGRATION_0004 = _load_migration("0004_material_status_columns.py")
MIGRATION_0005 = _load_migration("0005_drop_statuses.py")

MATERIAL_STATUSES = sa.text(
    "SELECT material_id, started_at, completed_at FROM materials "
    "WHERE started_at IS NOT NULL ORDER BY material_id",
)
LEGACY_STATUSES = sa.text(
    "SELECT material_id, started_at, completed_at FROM statuses ORDER BY material_id",
)
MATVIEW_STATUSES = sa.text(
    "SELECT material_status, count(*) FROM mvw_repeat_notes "
    "GROUP BY material_status ORDER BY material_status",
)


async def _in_rolled_back_migration[T](check: Callable[[Connection], T]) -> T:
    async with database.engine.connect() as conn:
        trans = await conn.begin()
        try:

            def _run(sync_conn: Connection) -> T:
                with Operations.context(MigrationContext.configure(sync_conn)):
                    return check(sync_conn)

            return await conn.run_sync(_run)
        finally:
            await trans.rollback()


def _rows(conn: Connection, query: sa.TextClause) -> list[tuple]:
    return [tuple(row) for row in conn.execute(query).all()]


async def test_downgrade_restores_statuses_from_materials():
    def check(conn: Connection) -> tuple[list[tuple], list[tuple]]:
        before = _rows(conn, MATERIAL_STATUSES)
        MIGRATION_0005.downgrade()
        MIGRATION_0004.downgrade()
        return before, _rows(conn, LEGACY_STATUSES)

    before, restored = await _in_rolled_back_migration(check)

    assert restored == before


async def test_downgrade_then_upgrade_keeps_statuses_and_matview():
    def check(conn: Connection) -> tuple[list[tuple], ...]:
        conn.execute(sa.text("REFRESH MATERIALIZED VIEW mvw_repeat_notes"))
        statuses_before = _rows(conn, MATERIAL_STATUSES)
        matview_before = _rows(conn, MATVIEW_STATUSES)

        MIGRATION_0005.downgrade()
        MIGRATION_0004.downgrade()
        legacy_matview = _rows(conn, MATVIEW_STATUSES)
        MIGRATION_0004.upgrade()
        MIGRATION_0005.upgrade()

        return (
            statuses_before,
            _rows(conn, MATERIAL_STATUSES),
            matview_before,
            legacy_matview,
            _rows(conn, MATVIEW_STATUSES),
        )

    statuses_before, statuses_after, matview_before, legacy, matview_after = (
        await _in_rolled_back_migration(check)
    )

    assert statuses_after == statuses_before
    assert legacy == matview_before
    assert matview_after == matview_before
