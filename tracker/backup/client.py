import datetime
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from grpc.aio import insecure_channel as grpc_chan

from tracker.common import database, settings
from tracker.common.logger import logger
from tracker.protos import backup_pb2, backup_pb2_grpc


LATEST = backup_pb2.BackupRef(latest=True)
DUMP_EXTENSIONS = {
    backup_pb2.BACKUP_FORMAT_PG_CUSTOM: "pgdump",
    backup_pb2.BACKUP_FORMAT_LEGACY_JSON_ZSTD: "json",
}
DUMP_TIME_FORMAT = "%Y-%m-%d_%H-%M-%S"


class BackupException(Exception):
    pass


@asynccontextmanager
async def _backup_stub() -> AsyncGenerator[backup_pb2_grpc.BackupStub]:
    async with grpc_chan(settings.BACKUP_TARGET) as channel:
        yield backup_pb2_grpc.BackupStub(channel)


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
        raise BackupException("Backup stream has no info message")
    return info, b"".join(chunks)


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def get_dump_filename(*, prefix: str = "tracker") -> Path:
    filename = f"{prefix}_{_utcnow().strftime(DUMP_TIME_FORMAT)}.json"
    return settings.DATA_DIR / filename


async def restore() -> None:
    logger.info("Restoring started")
    start_time = time.perf_counter()

    async with _backup_stub() as stub:
        reply: backup_pb2.RestoreReply = await stub.Restore(
            backup_pb2.RestoreRequest(backup=LATEST, confirm_db_name=settings.DB_NAME),
        )
    # pg_restore recreated tables and types; pooled connections hold stale OIDs.
    await database.engine.dispose()

    logger.info(
        "Restored from '%s' for %ss, previous state saved as '%s'",
        reply.restored.name,
        round(time.perf_counter() - start_time, 2),
        reply.pre_restore_backup.name,
    )


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
        raise BackupException(f"Unsupported backup format of '{info.name}'")

    filepath = get_dump_filename(prefix=prefix).with_suffix(f".{extension}")
    filepath.write_bytes(content)
    logger.info("Backup '%s' saved to %s", info.name, filepath)

    return filepath
