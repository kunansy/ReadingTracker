#!/usr/bin/env python3
import datetime
from pathlib import Path
from typing import NamedTuple, Any

import sqlalchemy.sql as sa
import ujson
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.ddl import DropTable, CreateTable
from sqlalchemy.sql.schema import Table

from tracker.common import database, settings, models
from tracker.common.log import logger


class TableSnapshot(NamedTuple):
    table_name: str
    rows: list[dict[str, str]]

    @property
    def counter(self) -> int:
        return len(self.rows)


class DBSnapshot(NamedTuple):
    tables: list[TableSnapshot]


DUMP_DATA = dict[str, list[dict[str, str]]]
TABLES = {
    models.Materials.name: models.Materials,
    models.Statuses.name: models.Statuses,
    models.ReadingLog.name: models.ReadingLog,
    models.Notes.name: models.Notes,
    models.Cards.name: models.Cards,
}


def _convert_date_to_str(value: Any) -> Any:
    if isinstance(value, datetime.date):
        return value.strftime(settings.DATE_FORMAT)
    if isinstance(value, datetime.datetime):
        return value.strftime(settings.DATETIME_FORMAT)
    return value


async def _get_table_snapshot(*,
                              table: Table,
                              conn: AsyncSession) -> TableSnapshot:
    stmt = sa.select(table)
    rows = [
        {
            str(key): _convert_date_to_str(value)
            for key, value in row.items()
        }
        for row in (await conn.execute(stmt)).mappings().all()
    ]
    return TableSnapshot(
        table_name=table.name,
        rows=rows
    )


async def get_db_snapshot() -> DBSnapshot:
    table_snapshots = []
    async with database.transaction() as ses:
        for table in TABLES.values():
            table_snapshot = await _get_table_snapshot(table=table, conn=ses)
            table_snapshots += [table_snapshot]

            logger.debug("%s: %s rows got", table.name, table_snapshot.counter)

    return DBSnapshot(tables=table_snapshots)


@compiles(DropTable, "postgresql")
def _compile_drop_table(element, compiler, **kwargs):
    return compiler.visit_drop_table(element) + " CASCADE"


async def _drop_tables(conn: AsyncSession) -> None:
    for table in TABLES.values():
        await conn.execute(DropTable(table))


async def _create_tables(conn: AsyncSession) -> None:
    for table in TABLES.values():
        await conn.execute(CreateTable(table))


async def recreate_db(conn: AsyncSession) -> None:
    await _drop_tables(conn)
    await _create_tables(conn)


def _convert_str_to_date(value: str) -> Any:
    try:
        return datetime.datetime.strptime(value, settings.DATETIME_FORMAT)
    except Exception:
        pass

    try:
        return datetime.datetime.strptime(value, settings.DATE_FORMAT).date()
    except Exception:
        pass

    return value


def _read_json_file(filepath: Path) -> dict[str, Any]:
    assert filepath.exists(), "File not found"
    assert filepath.suffix == '.json', "File must be json"

    with filepath.open() as f:
        return ujson.load(f)


def _get_now() -> str:
    now = datetime.datetime.utcnow()
    return now.strftime(settings.DATETIME_FORMAT).replace(' ', '_')


def dump_snapshot(snapshot: DBSnapshot) -> Path:
    logger.debug("DB dumping started")

    file_path = Path("data") / f"tracker_{_get_now()}.json"

    data = {
        table_snapshot.table_name: table_snapshot.rows
        for table_snapshot in snapshot.tables
    }
    with file_path.open('w') as f:
        ujson.dump(data, f, ensure_ascii=False, indent=2)

    logger.debug("DB dumped")

    return file_path


def _convert_dump_to_snapshot(dump_data: DUMP_DATA) -> DBSnapshot:
    tables = []
    for table_name, values in dump_data.items():
        rows = [
            {
                key: _convert_str_to_date(value)
                for key, value in row.items()
            }
            for row in values
        ]
        tables += [
            TableSnapshot(
                table_name=table_name,
                rows=rows
            )
        ]

    return DBSnapshot(tables=tables)


async def restore_db(*,
                     dump_path: Path,
                     conn: AsyncSession) -> DBSnapshot:
    if not dump_path.exists():
        raise ValueError("Dump file not found")

    dump_data = _read_json_file(dump_path)
    snapshot = _convert_dump_to_snapshot(dump_data)
    snapshot_dict = {
        table.table_name: table.rows
        for table in snapshot.tables
    }

    # order of them matters
    for table_name, table in TABLES.items():
        values = snapshot_dict[table_name]
        stmt = table.insert().values(values)
        await conn.execute(stmt)

        logger.debug("%s: %s rows inserted",
                     table.name, len(snapshot_dict[table_name]))
    return snapshot
