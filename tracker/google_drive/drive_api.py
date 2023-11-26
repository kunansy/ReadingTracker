import contextlib
import os
import tempfile
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, AsyncGenerator

import aiogoogle
import orjson
from aiogoogle.auth.creds import ServiceAccountCreds
from grpc.aio import insecure_channel as grpc_chan

from tracker.common import settings, database
from tracker.common.logger import logger
from tracker.google_drive import db
from tracker.protos import backup_pb2_grpc, backup_pb2


SCOPES = ["https://www.googleapis.com/auth/drive"]


class GoogleDriveException(Exception):
    pass


@lru_cache
def _get_drive_creds() -> ServiceAccountCreds:
    creds = ServiceAccountCreds(scopes=SCOPES, **settings.DRIVE_CREDS)

    return creds


@contextlib.asynccontextmanager
async def _drive_client() -> AsyncGenerator[
    tuple[aiogoogle.Aiogoogle, aiogoogle.GoogleAPI], None
]:
    creds = _get_drive_creds()

    async with aiogoogle.Aiogoogle(service_account_creds=creds) as client:
        drive_v3 = await client.discover("drive", "v3")
        try:
            yield client, drive_v3
        except Exception as e:
            logger.exception("Error with the client, %s", repr(e))
            raise GoogleDriveException(e) from e


async def _get_folder_id(*, folder_name: str = "tracker") -> str:
    async with _drive_client() as (client, drive):
        response = await client.as_service_account(
            drive.files.list(
                q=f"name = '{folder_name}'", spaces="drive", fields="files(id)"
            )
        )

    return response["files"][0]["id"]


async def _get_last_dump_id() -> str:
    logger.debug("Getting last dump started")
    folder_id = await _get_folder_id()
    query = f"name contains 'tracker_' and '{folder_id}' in parents"

    async with _drive_client() as (client, drive):
        response = await client.as_service_account(
            drive.files.list(
                q=query, spaces="drive", fields="files(id,modifiedTime,name)"
            )
        )
    files = response["files"]
    files.sort(key=lambda resp: resp["modifiedTime"], reverse=True)

    logger.debug("%s files found", len(files))
    return files[0]["id"]


async def _get_file_content(file_id: str) -> dict[str, Any]:
    logger.debug("Getting file id='%s'", file_id)

    tmp_file = tempfile.NamedTemporaryFile(delete=False)

    async with _drive_client() as (client, drive):
        await client.as_service_account(
            drive.files.get(fileId=file_id, download_file=tmp_file.name, alt="media"),
        )

    file = orjson.loads(tmp_file.read())

    tmp_file.close()
    os.remove(tmp_file.name)  # noqa: PL107
    return file


def _read_local_dump(filepath: Path) -> dict[str, Any]:
    if not filepath.exists():
        raise GoogleDriveException("%s file not found", filepath)

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
            dump = await get_dump()

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
        response: backup_pb2.BackupReply = await stub.Backup(
            backup_pb2.DBRequest(
                db_host=cfg.DB_HOST,
                db_port=cfg.DB_PORT,
                db_username=cfg.DB_USERNAME,
                db_password=cfg.DB_PASSWORD,
                db_name=cfg.DB_NAME,
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
