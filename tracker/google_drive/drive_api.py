import contextlib
import os
import tempfile
from functools import lru_cache
from typing import Any, AsyncGenerator

import aiogoogle
import orjson
from aiogoogle.auth.creds import ServiceAccountCreds
from grpc.aio import insecure_channel as grpc_chan

from tracker.common import settings
from tracker.common.logger import logger
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


async def get_dump() -> dict[str, Any]:
    async with grpc_chan(settings.BACKUP_TARGET) as channel:
        stub = backup_pb2_grpc.GoogleDriveStub(channel)
        response: backup_pb2.DownloadReply = await stub.DownloadLatestBackup(
            backup_pb2.Empty()
        )

    return orjson.loads(response.file_content)
