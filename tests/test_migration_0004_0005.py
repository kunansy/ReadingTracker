import datetime
import importlib.util
import uuid
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy.engine import Connection

from tracker.common import database, sort_keys
from tracker.models import enums, models


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


STARTED_AT = datetime.datetime(2024, 1, 4)  # noqa: DTZ001
COMPLETED_AT = datetime.datetime(2024, 2, 5)  # noqa: DTZ001
STATUS_IDS = sa.text("SELECT count(*), count(DISTINCT status_id) FROM statuses")


def _insert_material(
    conn: Connection,
    *,
    started_at: datetime.datetime | None,
    completed_at: datetime.datetime | None,
) -> str:
    material_id = str(uuid.uuid4())
    added_at = datetime.datetime(2024, 1, 1)  # noqa: DTZ001
    conn.execute(
        models.Materials.insert().values(
            material_id=material_id,
            title=f"Migration 0004 material {material_id}",
            authors="Author",
            pages=10,
            material_type=enums.MaterialTypesEnum.book,
            added_at=added_at,
            is_outlined=False,
            started_at=started_at,
            completed_at=completed_at,
            sort_key=sort_keys.material_sort_key(
                added_at=added_at,
                material_id=material_id,
            ),
        ),
    )
    return material_id


def _seed_materials(conn: Connection) -> dict[str, tuple]:
    """Insert a queued, a reading and a completed material, keyed by state."""
    states = {
        "queued": (None, None),
        "reading": (STARTED_AT, None),
        "completed": (STARTED_AT, COMPLETED_AT),
    }
    return {
        state: (
            uuid.UUID(_insert_material(conn, started_at=started, completed_at=completed)),
            started,
            completed,
        )
        for state, (started, completed) in states.items()
    }


def _seeded_rows(rows: list[tuple], seeded: dict[str, tuple]) -> set[tuple]:
    seeded_ids = {material_id for material_id, *_ in seeded.values()}
    return {row for row in rows if row[0] in seeded_ids}


async def test_downgrade_restores_statuses_from_materials():
    def check(conn: Connection) -> tuple[dict[str, tuple], list[tuple], list[tuple], tuple]:
        seeded = _seed_materials(conn)
        before = _rows(conn, MATERIAL_STATUSES)
        MIGRATION_0005.downgrade()
        MIGRATION_0004.downgrade()
        status_ids = tuple(conn.execute(STATUS_IDS).one())
        return seeded, before, _rows(conn, LEGACY_STATUSES), status_ids

    seeded, before, restored, (total, distinct) = await _in_rolled_back_migration(check)

    assert restored == before
    assert _seeded_rows(restored, seeded) == {seeded["reading"], seeded["completed"]}
    assert total == distinct == len(restored)


async def test_downgrade_then_upgrade_keeps_statuses_and_matview():
    def check(conn: Connection) -> tuple[list[tuple], ...]:
        seeded = _seed_materials(conn)
        conn.execute(sa.text("REFRESH MATERIALIZED VIEW mvw_repeat_notes"))
        statuses_before = _rows(conn, MATERIAL_STATUSES)
        matview_before = _rows(conn, MATVIEW_STATUSES)

        MIGRATION_0005.downgrade()
        MIGRATION_0004.downgrade()
        legacy_matview = _rows(conn, MATVIEW_STATUSES)
        MIGRATION_0004.upgrade()
        MIGRATION_0005.upgrade()

        return (
            seeded,
            statuses_before,
            _rows(conn, MATERIAL_STATUSES),
            matview_before,
            legacy_matview,
            _rows(conn, MATVIEW_STATUSES),
        )

    seeded, statuses_before, statuses_after, matview_before, legacy, matview_after = (
        await _in_rolled_back_migration(check)
    )

    assert statuses_after == statuses_before
    assert _seeded_rows(statuses_after, seeded) == {seeded["reading"], seeded["completed"]}
    assert legacy == matview_before
    assert matview_after == matview_before
