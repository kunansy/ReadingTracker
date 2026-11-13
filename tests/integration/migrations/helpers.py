"""Alembic and schema helpers for the migration tests."""

import asyncio
from pathlib import Path
from typing import Any

import sqlalchemy.sql as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from tests.integration import helpers
from tracker.common import database


REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = str(REPO_ROOT / "alembic.ini")
HEAD_REVISION = "0008"


def alembic_config(**kwargs: Any) -> Config:
    return Config(ALEMBIC_INI, **kwargs)


async def alembic_upgrade(revision: str) -> None:
    # env.py calls asyncio.run(), which needs a thread without a running loop
    await asyncio.to_thread(command.upgrade, alembic_config(), revision)
    # pooled connections cache statements prepared against the previous schema
    await database.engine.dispose()


async def alembic_downgrade(revision: str) -> None:
    await asyncio.to_thread(command.downgrade, alembic_config(), revision)
    await database.engine.dispose()


async def current_revision() -> str | None:
    if not await helpers.scalar("SELECT to_regclass('alembic_version')"):
        return None
    return await helpers.scalar("SELECT version_num FROM alembic_version")


async def drop_everything() -> None:
    async with database.engine.begin() as conn:
        await conn.execute(sa.text("DROP SCHEMA public CASCADE"))
        await conn.execute(sa.text("CREATE SCHEMA public"))
    # pooled connections cache statements prepared against the dropped tables
    await database.engine.dispose()


async def reset_schema_to_head() -> None:
    """Leave the database as the session fixture made it: migrated to head, empty tables."""
    await drop_everything()
    await database.create_db()
    await database.engine.dispose()


async def schema_snapshot() -> dict[str, Any]:
    """Columns, indexes and unique constraints of every table, to compare two schemas."""

    def snapshot(sync_conn) -> dict[str, Any]:  # noqa: ANN001
        inspector = inspect(sync_conn)
        return {
            table: {
                "columns": {
                    column["name"]: (str(column["type"]), column["nullable"])
                    for column in inspector.get_columns(table)
                },
                "indexes": {
                    index["name"]: (tuple(index["column_names"]), index["unique"])
                    for index in inspector.get_indexes(table)
                },
                "unique": {
                    constraint["name"]: tuple(constraint["column_names"])
                    for constraint in inspector.get_unique_constraints(table)
                },
            }
            for table in sorted(inspector.get_table_names())
        }

    async with database.engine.connect() as conn:
        return await conn.run_sync(snapshot)
