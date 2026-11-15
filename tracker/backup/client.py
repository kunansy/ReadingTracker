import asyncio
import datetime
import time
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import BinaryIO

from grpc.aio import (
    AioRpcError,
    insecure_channel as grpc_chan,
)

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
async def _rpc_errors() -> AsyncGenerator[None]:
    try:
        yield
    except AioRpcError as e:
        raise BackupException(
            f"Backup service error: {e.code().name}: {e.details()}",
        ) from e


@asynccontextmanager
async def _backup_stub() -> AsyncGenerator[backup_pb2_grpc.BackupStub]:
    async with grpc_chan(settings.BACKUP_TARGET) as channel:
        yield backup_pb2_grpc.BackupStub(channel)


def _elapsed(start: float) -> float:
    return round(time.perf_counter() - start, 2)


async def _download(
    stub: backup_pb2_grpc.BackupStub,
    ref: backup_pb2.BackupRef,
    sink: BinaryIO,
) -> backup_pb2.BackupInfo:
    info: backup_pb2.BackupInfo | None = None

    async for chunk in stub.DownloadBackup(ref, timeout=settings.BACKUP_RESTORE_TIMEOUT):
        if chunk.HasField("info"):
            info = chunk.info
        elif chunk.data:
            await asyncio.to_thread(sink.write, chunk.data)

    if info is None:
        raise BackupException("Backup stream has no info message")
    return info


def _dump_extension(info: backup_pb2.BackupInfo) -> str:
    if (extension := DUMP_EXTENSIONS.get(info.format)) is None:
        raise BackupException(f"Unsupported backup format of '{info.name}'")
    return extension


def get_dump_filename(*, prefix: str, extension: str, now: datetime.datetime) -> Path:
    filename = f"{prefix}_{now.strftime(DUMP_TIME_FORMAT)}.{extension}"
    return settings.DATA_DIR / filename


async def _dispose_engine_after_failed_restore() -> None:
    # pg_restore may have recreated tables and types even when the call failed,
    # so pooled connections can hold stale OIDs.
    try:
        await database.engine.dispose()
    except Exception:
        logger.exception("Engine dispose after restore failed")


async def restore() -> None:
    logger.info("Restore started")
    start = time.perf_counter()

    try:
        async with _rpc_errors(), _backup_stub() as stub:
            reply: backup_pb2.RestoreReply = await stub.Restore(
                backup_pb2.RestoreRequest(
                    backup=LATEST,
                    confirm_db_name=settings.DB_NAME,
                ),
                timeout=settings.BACKUP_RESTORE_TIMEOUT,
            )
    except BaseException:
        await _dispose_engine_after_failed_restore()
        raise

    try:
        await database.engine.dispose()
    except Exception as e:
        raise BackupException("Engine dispose after restore failed") from e

    logger.info(
        "Restore completed for %ss from '%s', previous state saved as '%s'",
        _elapsed(start),
        reply.restored.name,
        reply.pre_restore_backup.name,
    )


async def backup() -> str:
    logger.info("Backup started")
    start = time.perf_counter()

    async with _rpc_errors(), _backup_stub() as stub:
        info: backup_pb2.BackupInfo = await stub.CreateBackup(
            backup_pb2.CreateBackupRequest(),
            timeout=settings.BACKUP_TIMEOUT,
        )

    logger.info("Backup completed for %ss, file_id: '%s'", _elapsed(start), info.id)

    return info.id


async def download_latest(
    *,
    prefix: str = "last_dump",
    clock: Callable[[], datetime.datetime] = database.utcnow,
) -> Path:
    """Save the latest backup to DATA_DIR: `.pgdump`, or `.json` server-decompressed."""
    partial = settings.DATA_DIR / f".{prefix}.partial"

    try:
        sink = await asyncio.to_thread(partial.open, "wb")
        with sink:
            async with _rpc_errors(), _backup_stub() as stub:
                info = await _download(stub, LATEST, sink)

        filepath = get_dump_filename(
            prefix=prefix,
            extension=_dump_extension(info),
            now=clock(),
        )
        await asyncio.to_thread(partial.rename, filepath)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise

    logger.info("Backup '%s' saved to %s", info.name, filepath)
    return filepath
