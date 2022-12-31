import contextlib
import io
import os
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any, AsyncGenerator

import aiogoogle
import orjson
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
from aiogoogle.auth.creds import ServiceAccountCreds

from tracker.common import settings
from tracker.common.log import logger


SCOPES = ['https://www.googleapis.com/auth/drive']


class GoogleDriveException(Exception):
    pass


@lru_cache
def _get_drive_creds() -> ServiceAccountCreds:
    if not (creds_file := settings.DRIVE_CREDS_PATH).exists():
        raise ValueError("Creds file not found")

    creds_json = orjson.loads(creds_file.read_text())
    creds = ServiceAccountCreds(
        scopes=SCOPES,
        **creds_json
    )

    return creds


@contextlib.asynccontextmanager
async def _drive_client() -> AsyncGenerator[tuple[aiogoogle.Aiogoogle, aiogoogle.GoogleAPI], None]:
    creds = _get_drive_creds()

    async with aiogoogle.Aiogoogle(service_account_creds=creds) as client:
        drive_v3 = await client.discover('drive', 'v3')
        try:
            yield client, drive_v3
        except Exception as e:
            logger.exception("Error with the client, %s", repr(e))
            raise GoogleDriveException(e) from e


async def _get_folder_id(*,
                         folder_name: str = 'tracker') -> str:
    async with _drive_client() as (client, drive):
        response = await client.as_service_account(
            drive.files.list(
                q=f"name = '{folder_name}'", spaces='drive', fields='files(id)')
        )

    return response['files'][0]['id']


def _dict_to_io(value: dict[str, Any]) -> io.BytesIO:
    return io.BytesIO(orjson.dumps(value))


async def send_dump(*,
                    dump: dict[str, Any],
                    filename: Path) -> None:
    logger.debug("Sending file %s", filename)

    file_metadata = {
        'name': f"{filename.name}",
        'parents': [await _get_folder_id()]
    }

    tmp_file = tempfile.NamedTemporaryFile(mode="wb", delete=False)
    tmp_file.write(orjson.dumps(dump))
    tmp_file.close()

    async with _drive_client() as (client, drive):
        await client.as_service_account(
            drive.files.create(
                upload_file=tmp_file.name, json=file_metadata))

    os.remove(tmp_file.name)
    logger.debug("File sent")


def _get_last_dump_id() -> str:
    logger.debug("Getting last dump started")
    folder_id = _get_folder_id()
    query = f"name contains 'tracker_' and mimeType='application/json' and '{folder_id}' in parents"

    with _drive_client() as client:
        response = client.files().list(
            q=query, spaces='drive', fields='files(id,modifiedTime,name)') \
            .execute()
    files = response['files']
    files.sort(key=lambda resp: resp['modifiedTime'], reverse=True)

    logger.debug("%s files found", len(files))
    return files[0]['id']


def _get_file_content(file_id: str) -> dict[str, Any]:
    logger.debug("Getting file id='%s'", file_id)

    with _drive_client() as client:
        request = client.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
            logger.debug("Getting %d%%.", int(status.progress() * 100))

        fh.seek(0)

    return orjson.loads(fh.read().decode())


def get_dump() -> dict[str, Any]:
    if not (dump_file_id := _get_last_dump_id()):
        raise ValueError("Dump not found")

    return _get_file_content(dump_file_id)
