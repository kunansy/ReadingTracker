import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import orjson
from grpc.aio import insecure_channel as grpc_chan

from tracker.common import database, settings
from tracker.common.logger import logger
from tracker.google_drive import db
from tracker.google_drive.db import DBSnapshot
from tracker.protos import backup_pb2, backup_pb2_grpc


LATEST = backup_pb2.BackupRef(latest=True)
DUMP_EXTENSIONS = {
    backup_pb2.BACKUP_FORMAT_PG_CUSTOM: "pgdump",
    backup_pb2.BACKUP_FORMAT_LEGACY_JSON_ZSTD: "json",
}


class GoogleDriveException(Exception):
    pass


@asynccontextmanager
async def _backup_stub() -> AsyncGenerator[backup_pb2_grpc.BackupStub]:
    async with grpc_chan(settings.BACKUP_TARGET) as channel:
        yield backup_pb2_grpc.BackupStub(channel)


def _read_local_dump(filepath: Path) -> dict[str, Any]:
    if not filepath.exists():
        raise GoogleDriveException(f"{filepath} file not found")

    with filepath.open() as f:
        return orjson.loads(f.read())


async def _download(
    stub: backup_pb2_grpc.BackupStub,
    ref: backup_pb2.BackupRef,
) -> tuple[backup_pb2.BackupInfo, bytes]:
    info: backup_pb2.BackupInfo | None = None
    chunks: list[bytes] = []

    async for chunk in stub.DownloadBackup(ref):
        if chunk.HasField("info"):
            info = chunk.info
        else:
            chunks.append(chunk.data)

    if info is None:
        raise GoogleDriveException("Backup stream has no info message")
    return info, b"".join(chunks)


async def _restore_legacy(dump: dict[str, Any]) -> None:
    snapshot = DBSnapshot.from_dump(dump)
    async with database.transaction() as ses:
        await database.recreate_db()
        await db.restore_db(conn=ses, snapshot=snapshot)
        snapshot_dict = snapshot.to_dict()

        logger.debug("Set notes sequence value")
        await db.set_notes_seq_value(snapshot_dict["notes"], ses)

        logger.debug("Creating repeat notes material view")
        await database.create_repeat_notes_matview(ses)


async def _restore_from_service(stub: backup_pb2_grpc.BackupStub) -> None:
    info: backup_pb2.BackupInfo = await stub.GetBackup(LATEST)
    ref = backup_pb2.BackupRef(id=info.id)
    logger.info("Restoring from '%s'", info.name)

    if info.format == backup_pb2.BACKUP_FORMAT_PG_CUSTOM:
        reply: backup_pb2.RestoreReply = await stub.Restore(
            backup_pb2.RestoreRequest(backup=ref, confirm_db_name=settings.DB_NAME),
        )
        # pg_restore recreated tables and types; pooled connections hold stale OIDs.
        await database.engine.dispose()
        logger.info(
            "Restored from '%s', previous state saved as '%s'",
            reply.restored.name,
            reply.pre_restore_backup.name,
        )
    elif info.format == backup_pb2.BACKUP_FORMAT_LEGACY_JSON_ZSTD:
        _, content = await _download(stub, ref)
        await _restore_legacy(orjson.loads(content))
    else:
        raise GoogleDriveException(f"Unsupported backup format of '{info.name}'")


async def restore(*, dump_path: Path | None = None) -> None:
    logger.info("Restoring started")
    start_time = time.perf_counter()

    if dump_path:
        await _restore_legacy(_read_local_dump(dump_path))
    else:
        async with _backup_stub() as stub:
            await _restore_from_service(stub)

    logger.info("Restoring completed, %ss", round(time.perf_counter() - start_time, 2))


async def backup() -> str:
    start = time.perf_counter()

    async with _backup_stub() as stub:
        info: backup_pb2.BackupInfo = await stub.CreateBackup(
            backup_pb2.CreateBackupRequest(),
        )

    exec_time = round(time.perf_counter() - start, 2)
    logger.info("Backup completed for %ss, file_id: '%s'", exec_time, info.id)

    return info.id


async def download_latest(*, prefix: str = "last_dump") -> Path:
    """Save the latest backup to DATA_DIR: `.pgdump` or decompressed legacy `.json`."""
    async with _backup_stub() as stub:
        info, content = await _download(stub, LATEST)

    extension = DUMP_EXTENSIONS.get(info.format)
    if extension is None:
        raise GoogleDriveException(f"Unsupported backup format of '{info.name}'")

    filepath = db.get_dump_filename(prefix=prefix).with_suffix(f".{extension}")
    filepath.write_bytes(content)
    logger.info("Backup '%s' saved to %s", info.name, filepath)

    return filepath
