#!/usr/bin/env python3
import argparse
import asyncio
import datetime
import os
import time
from pathlib import Path
from typing import Any, NamedTuple

import sqlalchemy.sql as sa
import ujson
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.ddl import DropTable, CreateTable
from sqlalchemy.sql.schema import Table

from tracker.common import database, models, settings
from tracker.google_drive import drive_api
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

SCOPES = ['https://www.googleapis.com/auth/drive']
TABLES = {
    models.Materials.name: models.Materials,
    models.Statuses.name: models.Statuses,
    models.ReadingLog.name: models.ReadingLog,
    models.Notes.name: models.Notes,
    models.Cards.name: models.Cards,
}


def _get_now() -> str:
    now = datetime.datetime.utcnow()
    return now.strftime(settings.DATETIME_FORMAT).replace(' ', '_')


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


async def _get_db_snapshot() -> DBSnapshot:
    table_snapshots = []
    async with database.transaction() as ses:
        for table in TABLES.values():
            table_snapshot = await _get_table_snapshot(table=table, conn=ses)
            table_snapshots += [table_snapshot]

            logger.debug("%s: %s rows got", table.name, table_snapshot.counter)

    return DBSnapshot(tables=table_snapshots)


def _dump_snapshot(snapshot: DBSnapshot) -> Path:
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


def _remove_file(file_path: Path) -> None:
    logger.debug("Removing '%s'", file_path)
    os.remove(file_path)
    logger.debug("File removed")


async def backup() -> DBSnapshot:
    logger.info("Backuping started")
    start_time = time.perf_counter()

    db_snapshot = await _get_db_snapshot()
    dump_file = _dump_snapshot(db_snapshot)
    drive_api._send_dump(dump_file)
    _remove_file(dump_file)

    logger.info("Backuping completed, %ss",
                round(time.perf_counter() - start_time, 2))

    return db_snapshot


@compiles(DropTable, "postgresql")
def _compile_drop_table(element, compiler, **kwargs):
    return compiler.visit_drop_table(element) + " CASCADE"


async def _drop_tables(conn: AsyncSession) -> None:
    for table in TABLES.values():
        await conn.execute(DropTable(table))


async def _create_tables(conn: AsyncSession) -> None:
    for table in TABLES.values():
        await conn.execute(CreateTable(table))


async def _recreate_db(conn: AsyncSession) -> None:
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


async def _restore_db(*,
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


def _get_local_dump_file(filepath: Path) -> Path:
    if 'data/' not in str(filepath):
        filepath = Path('data') / filepath

    assert filepath.exists(), f"File {filepath=} not found"

    return filepath


async def restore(*,
                  dump_path: Path | None = None) -> DBSnapshot:
    logger.info("Restoring started")
    start_time = time.perf_counter()

    async with database.transaction() as ses:
        if dump_path:
            filepath = _get_local_dump_file(dump_path)
        else:
            filepath = drive_api._get_google_dump_file()

        await _recreate_db(conn=ses)
        snapshot = await _restore_db(conn=ses, dump_path=filepath)

        logger.info("Restoring completed, %ss",
                    round(time.perf_counter() - start_time, 2))

        if dump_path:
            _remove_file(dump_path)
    return snapshot


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backup/restore the database"
    )
    parser.add_argument(
        '--backup',
        help="Create and send a backup to the Google Drive",
        action="store_true",
        dest="backup"
    )
    parser.add_argument(
        '--restore',
        help="Download the last backup from the Google Drive and restore the database",
        action="store_true",
        dest="restore"
    )
    parser.add_argument(
        '--backup-offline',
        help="Dump the database to the local file",
        action="store_true",
        dest="backup_offline",
    )
    parser.add_argument(
        '--restore-offline',
        help="Restore the database from the local file",
        type=Path,
        dest="restore_offline",
    )
    parser.add_argument(
        '--get-last-dump',
        help="Download the last backup from the Google Drive",
        action="store_true",
        dest="last_dump"
    )
    args = parser.parse_args()

    if args.backup:
        await backup()
    elif args.restore:
        await restore()
    elif args.last_dump:
        last_dump_id = drive_api._get_last_dump()
        drive_api._download_file(last_dump_id, filename='last_dump.json')
    elif dump_path := args.restore_offline:
        await restore(dump_path=dump_path)
    elif args.backup_offline:
        snapshot = await _get_db_snapshot()
        _dump_snapshot(snapshot)


if __name__ == "__main__":
    asyncio.run(main())
