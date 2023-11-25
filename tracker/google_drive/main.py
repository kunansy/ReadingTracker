#!/usr/bin/env python3
import argparse
import asyncio
import time
from pathlib import Path
from typing import Any

import orjson
from grpc.aio import insecure_channel as grpc_chan

from tracker.common import database
from tracker.common.logger import logger
from tracker.google_drive import db, drive_api
from tracker.protos import backup_pb2, backup_pb2_grpc


def _read_local_dump(filepath: Path) -> dict[str, Any]:
    if not filepath.exists():
        raise drive_api.GoogleDriveException("%s file not found", filepath)

    with filepath.open() as f:
        return orjson.loads(f.read())


def _dump_json(data: dict[str, Any], *, filepath: Path) -> None:
    dump_data = orjson.dumps(data)
    with filepath.open("wb") as f:
        f.write(dump_data)


async def restore(*, dump_path: Path | None = None) -> db.DBSnapshot:
    logger.info("Restoring started")
    start_time = time.perf_counter()

    async with database.transaction() as ses:
        if dump_path:
            dump = _read_local_dump(dump_path)
        else:
            dump = await drive_api.get_dump()

        await database.recreate_db()
        snapshot = await db.restore_db(conn=ses, dump=dump)

        logger.info(
            "Restoring completed, %ss", round(time.perf_counter() - start_time, 2)
        )

    return snapshot


async def backup() -> str | None:
    import tracker.common.settings as cfg

    start = time.perf_counter()

    async with grpc_chan(cfg.BACKUP_TARGET) as channel:
        stub = backup_pb2_grpc.GoogleDriveStub(channel)
        response = await stub.Backup(
            backup_pb2.BackupRequest(
                db_host=cfg.DB_HOST,
                db_port=cfg.DB_PORT,
                db_username=cfg.DB_USERNAME,
                db_password=cfg.DB_PASSWORD,
                db_name=cfg.DB_NAME,
                delete_after=False,
            )
        )

    file_id = getattr(response, "file_id", None)
    exec_time = round(time.perf_counter() - start, 2)
    logger.info("Backup completed for %ss, file_id: '%s'", exec_time, file_id)

    return file_id


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backup/restore the database")
    parser.add_argument(
        "--backup",
        help="Create and send a backup to the Google Drive",
        action="store_true",
        dest="backup",
    )
    parser.add_argument(
        "--restore",
        help="Download the last backup from the Google Drive and restore the database",
        action="store_true",
        dest="restore",
    )
    parser.add_argument(
        "--backup-offline",
        help="Dump the database to the local file",
        action="store_true",
        dest="backup_offline",
    )
    parser.add_argument(
        "--restore-offline",
        help="Restore the database from the local file",
        type=Path,
        dest="restore_offline",
    )
    parser.add_argument(
        "--get-last-dump",
        help="Download the last backup from the Google Drive",
        action="store_true",
        dest="get_last_dump",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    if args.backup:
        raise NotImplementedError
    elif args.restore:
        await restore()
    elif args.get_last_dump:
        dump = await drive_api.get_dump()
        filepath = db.get_dump_filename(prefix="last_dump")
        _dump_json(dump, filepath=filepath)
    elif dump_path := args.restore_offline:
        await restore(dump_path=dump_path)
    elif args.backup_offline:
        raise NotImplementedError


if __name__ == "__main__":
    asyncio.run(main())
