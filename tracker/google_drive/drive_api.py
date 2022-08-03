import contextlib
import io
from functools import lru_cache
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

from tracker.common import settings
from tracker.common.log import logger

SCOPES = ['https://www.googleapis.com/auth/drive']


@lru_cache
def _get_drive_creds() -> Credentials:
    creds = None
    if settings.DRIVE_TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(
            settings.DRIVE_TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(
            settings.DRIVE_CREDS_PATH, SCOPES)
        creds = flow.run_local_server(port=0)

        # dump token if it was updated
        with settings.DRIVE_TOKEN_PATH.open('w') as token:
            token.write(creds.to_json())

    return creds


@contextlib.contextmanager
def _drive_client():
    creds = _get_drive_creds()

    new_client = build('drive', 'v3', credentials=creds)
    try:
        yield new_client
    except Exception:
        logger.exception("Error with the client")
        raise


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


def get_last_dump() -> str:
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


def download_file(file_id: str,
                  *,
                  filename: str = 'restore.json') -> Path:
    logger.debug("Downloading file id='%s'", file_id)
    path = Path('data') / filename

    with _drive_client() as client:
        request = client.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
            logger.debug("Download %d%%.", int(status.progress() * 100))

        fh.seek(0)
        with path.open('wb') as f:
            f.write(fh.read())
    return path


def get_google_dump_file() -> Path:
    if not (dump_file_id := get_last_dump()):
        raise ValueError("Dump not found")

    return download_file(dump_file_id)
