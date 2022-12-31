#!/usr/bin/env python3
import argparse
import asyncio
import time
from pathlib import Path
from typing import Any

import orjson

from tracker.common import database
from tracker.common.log import logger
from tracker.google_drive import drive_api, db


async def backup() -> db.DBSnapshot:
    logger.info("Backuping started")
    start_time = time.perf_counter()

    db_snapshot = await db.get_db_snapshot()
    filename = db.get_dump_filename()

    await drive_api.send_dump(
        dump=db_snapshot.table_to_rows(),
        filename=filename
    )

    logger.info("Backuping completed, %ss",
                round(time.perf_counter() - start_time, 2))

    return db_snapshot


def _read_local_dump(filepath: Path) -> dict[str, Any]:
    if not filepath.exists():
        raise drive_api.GoogleDriveException("%s file not found", filepath)

    with filepath.open() as f:
        return orjson.loads(f.read())


def _dump_json(data: dict[str, Any],
               *,
               filepath: Path) -> None:
    dump_data = orjson.dumps(data)
    with filepath.open('wb') as f:
        f.write(dump_data)


async def restore(*,
                  dump_path: Path | None = None) -> db.DBSnapshot:
    logger.info("Restoring started")
    start_time = time.perf_counter()

    async with database.transaction() as ses:
        if dump_path:
            dump = _read_local_dump(dump_path)
        else:
            dump = await drive_api.get_dump()

        await db.recreate_db()
        snapshot = await db.restore_db(conn=ses, dump=dump)

        logger.info("Restoring completed, %ss",
                    round(time.perf_counter() - start_time, 2))

    return snapshot


def parse_args() -> argparse.Namespace:
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
        dest="get_last_dump"
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    if args.backup:
        await backup()
    elif args.restore:
        await restore()
    elif args.get_last_dump:
        dump = await drive_api.get_dump()
        filepath = db.get_dump_filename(prefix='last_dump')
        _dump_json(dump, filepath=filepath)
    elif dump_path := args.restore_offline:
        await restore(dump_path=dump_path)
    elif args.backup_offline:
        snapshot = await db.get_db_snapshot()
        filepath = db.get_dump_filename(prefix='offline_backup')
        _dump_json(snapshot.table_to_rows(), filepath=filepath)


if __name__ == "__main__":
    asyncio.run(main())
