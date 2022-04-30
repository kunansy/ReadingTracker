#!/usr/bin/env python3
import argparse
import asyncio
import os
import time
from pathlib import Path

from tracker.common import database
from tracker.common.log import logger
from tracker.google_drive import drive_api, db


def _remove_file(file_path: Path) -> None:
    logger.debug("Removing '%s'", file_path)
    os.remove(file_path)
    logger.debug("File removed")


async def backup() -> db.DBSnapshot:
    logger.info("Backuping started")
    start_time = time.perf_counter()

    db_snapshot = await db._get_db_snapshot()
    dump_file = db._dump_snapshot(db_snapshot)
    drive_api.send_dump(dump_file)
    _remove_file(dump_file)

    logger.info("Backuping completed, %ss",
                round(time.perf_counter() - start_time, 2))

    return db_snapshot


def _get_local_dump_file(filepath: Path) -> Path:
    if 'data/' not in str(filepath):
        filepath = Path('data') / filepath

    assert filepath.exists(), f"File {filepath=} not found"

    return filepath


async def restore(*,
                  dump_path: Path | None = None) -> db.DBSnapshot:
    logger.info("Restoring started")
    start_time = time.perf_counter()

    async with database.transaction() as ses:
        if dump_path:
            filepath = _get_local_dump_file(dump_path)
        else:
            filepath = drive_api.get_google_dump_file()

        await db._recreate_db(conn=ses)
        snapshot = await db._restore_db(conn=ses, dump_path=filepath)

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
        drive_api.get_google_dump_file()
    elif dump_path := args.restore_offline:
        await restore(dump_path=dump_path)
    elif args.backup_offline:
        snapshot = await db._get_db_snapshot()
        db._dump_snapshot(snapshot)


if __name__ == "__main__":
    asyncio.run(main())