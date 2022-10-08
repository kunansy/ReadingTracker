import contextlib
import io
from functools import lru_cache
from pathlib import Path
from typing import Any

import orjson
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

from tracker.common import settings
from tracker.common.log import logger


SCOPES = ['https://www.googleapis.com/auth/drive']


class GoogleDriveException(Exception):
    pass


@lru_cache
def _get_drive_creds() -> Credentials:
    if not (creds_file := settings.DRIVE_CREDS_PATH).exists():
        raise ValueError("Creds file not found")

    creds = Credentials.from_service_account_file(
        creds_file, scopes=SCOPES)

    return creds


@contextlib.contextmanager
def _drive_client():
    creds = _get_drive_creds()

    new_client = build('drive', 'v3', credentials=creds)
    try:
        yield new_client
    except Exception as e:
        logger.exception("Error with the client, %s", repr(e))
        raise GoogleDriveException(e) from e


def _get_folder_id(*,
                   folder_name: str = 'tracker') -> str:
    with _drive_client() as client:
        response = client.files().list(
            q=f"name = '{folder_name}'", spaces='drive', fields='files(id)').execute()
    return response['files'][0]['id']


def send_dump(file_path: Path) -> None:
    logger.debug("Sending file %s", file_path)

    file_metadata = {
        'name': f"{file_path.name}",
        'parents': [_get_folder_id()]
    }
    file = MediaFileUpload(
        file_path, mimetype='application/json')

    with _drive_client() as client:
        client.files().create(
            body=file_metadata, media_body=file).execute()
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

def get_dump_file() -> Path:
    if not (dump_file_id := _get_last_dump_id()):
        raise ValueError("Dump not found")

    return _download_file(dump_file_id)
