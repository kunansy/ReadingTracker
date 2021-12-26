#!/usr/bin/env python3
import asyncio
import contextlib
import datetime
import os
import time
from pathlib import Path
from typing import Any

import sqlalchemy.sql as sa
import ujson
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from tracker.common import database, models, settings
from tracker.common.log import logger


TABLES = [
    models.Materials,
    models.Statuses,
    models.ReadingLog,
    models.Notes,
    models.Cards,
]


def get_now() -> str:
    now = datetime.datetime.utcnow()
    return now.strftime('%Y-%m-%d_%H-%M-%S')


def convert_date(value: Any) -> Any:
    if isinstance(value, datetime.date):
        return value.strftime(settings.DATE_FORMAT)
    if isinstance(value, datetime.datetime):
        return value.strftime(settings.DATETIME_FORMAT)
    return value


async def get_data() -> dict[str, list[dict[str, str]]]:
    data = {}
    async with database.session() as ses:
        for table in TABLES:
            stmt = sa.select(table)
            data[table.name] = [
                {str(key): convert_date(value) for key, value in row.items()}
                for row in (await ses.execute(stmt)).mappings().all()
            ]
    return data


async def dump() -> Path:
    logger.debug("DB dumping started")

    file_path = Path("data") / f"tracker_{get_now()}.json"
    data = await get_data()

    with file_path.open('w') as f:
        ujson.dump(data, f, ensure_ascii=False, indent=2)

    logger.debug("DB dumped")

    return file_path


@contextlib.contextmanager
def get_client():
    scopes = ['https://www.googleapis.com/auth/drive']
    creds = None
    if settings.DRIVE_TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(
            settings.DRIVE_TOKEN_PATH, scopes)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                settings.DRIVE_CREDS_PATH, scopes)
            creds = flow.run_local_server(port=0)

        with settings.DRIVE_TOKEN_PATH.open('w') as token:
            token.write(creds.to_json())

    new_client = build('drive', 'v3', credentials=creds)
    try:
        yield new_client
    except Exception:
        logger.exception("Error with the client")


def get_folder_id() -> str:
    with get_client() as client:
        response = client.files().list(
            q="name = 'tracker'", spaces='drive', fields='files(id)').execute()
    return response['files'][0]['id']


def send_dump(file_path: Path) -> None:
    logger.debug("Sending file %s", file_path)
    with get_client() as client:
        file_metadata = {
            'name': f"{file_path.name}",
            'parents': [get_folder_id()]
        }
        file = MediaFileUpload(file_path, mimetype='application/json')
        client.files().create(
            body=file_metadata, media_body=file).execute()
    logger.debug("File sent")


def remove_file(file_path: Path) -> None:
    logger.debug("Removing '%s'", file_path)
    os.remove(file_path)
    logger.debug("File removed")


async def main() -> None:
    logger.info("Dumping started")
    start_time = time.perf_counter()

    dump_file = await dump()
    send_dump(dump_file)
    remove_file(dump_file)

    logger.info("Dumping completed, %ss",
                round(time.perf_counter() - start_time, 2))


def get_last_dump() -> Path:
    pass


async def restore_db(dump_path: Path) -> None:
    pass


async def restore() -> None:
    logger.info("Restoring started")
    start_time = time.perf_counter()

    if not (dump_file := get_last_dump()):
        raise ValueError("Dump not found")
    await restore_db(dump_file)
    remove_file(dump_file)

    logger.info("Restoring completed, %ss",
                round(time.perf_counter() - start_time, 2))


if __name__ == "__main__":
    asyncio.run(main())
