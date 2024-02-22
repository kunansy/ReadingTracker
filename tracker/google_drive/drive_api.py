import time
from pathlib import Path
from typing import Any

import orjson
from grpc.aio import insecure_channel as grpc_chan

from tracker.common import database, settings
from tracker.common.logger import logger
from tracker.google_drive import db
from tracker.google_drive.db import DBSnapshot
from tracker.protos import backup_pb2, backup_pb2_grpc


class GoogleDriveException(Exception):
    pass


def _read_local_dump(filepath: Path) -> dict[str, Any]:
    if not filepath.exists():
        raise GoogleDriveException("%s file not found", filepath)

    with filepath.open() as f:
        return orjson.loads(f.read())


def dump_json(data: dict[str, Any], *, filepath: Path) -> None:
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
            dump = await get_dump()

        snapshot = DBSnapshot.from_dump(dump)

        await database.recreate_db()
        await db.restore_db(conn=ses, snapshot=snapshot)
        snapshot_dict = snapshot.to_dict()

        logger.debug("Set notes sequence value")
        await db.set_notes_seq_value(snapshot_dict["notes"], ses)

        logger.debug("Set materials sequence value")
        await db.set_materials_seq_value(snapshot_dict["materials"], ses)

        logger.info(
            "Restoring completed, %ss", round(time.perf_counter() - start_time, 2)
        )

    return snapshot


async def backup() -> str | None:
    start = time.perf_counter()

    async with grpc_chan(settings.BACKUP_TARGET) as channel:
        stub = backup_pb2_grpc.GoogleDriveStub(channel)
        response: backup_pb2.BackupReply = await stub.Backup(
            backup_pb2.DBRequest(
                db_host=settings.DB_HOST,
                db_port=settings.DB_PORT,
                db_username=settings.DB_USERNAME,
                db_password=settings.DB_PASSWORD,
                db_name=settings.DB_NAME,
            )
        )

    file_id = response.file_id
    exec_time = round(time.perf_counter() - start, 2)
    logger.info("Backup completed for %ss, file_id: '%s'", exec_time, file_id)

    return file_id


async def get_dump() -> dict[str, Any]:
    async with grpc_chan(settings.BACKUP_TARGET) as channel:
        stub = backup_pb2_grpc.GoogleDriveStub(channel)
        response: backup_pb2.DownloadReply = await stub.DownloadLatestBackup(
            backup_pb2.Empty()
        )

    return orjson.loads(response.file_content)
