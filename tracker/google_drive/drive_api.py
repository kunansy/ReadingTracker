#!/usr/bin/env python3
import asyncio
import argparse
import contextlib
import datetime
import io
import os
import time
from pathlib import Path
from typing import Any
from functools import lru_cache

import sqlalchemy.sql as sa
import ujson
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.ddl import DropTable

from tracker.common import database, models, settings
from tracker.common.log import logger


SNAPSHOT = dict[str, list[dict[str, str]]]

SCOPES = ['https://www.googleapis.com/auth/drive']
TABLES = [
    models.Materials,
    models.Statuses,
    models.ReadingLog,
    models.Notes,
    models.Cards,
]


def _get_now() -> str:
    now = datetime.datetime.utcnow()
    return now.strftime(settings.DATETIME_FORMAT).replace(' ', '_')


def _convert_date_to_str(value: Any) -> Any:
    if isinstance(value, datetime.date):
        return value.strftime(settings.DATE_FORMAT)
    if isinstance(value, datetime.datetime):
        return value.strftime(settings.DATETIME_FORMAT)
    return value


async def _get_db_snapshot() -> SNAPSHOT:
    data = {}
    async with database.session() as ses:
        for table in TABLES:
            stmt = sa.select(table)
            data[table.name] = [
                {
                    str(key): _convert_date_to_str(value)
                    for key, value in row.items()
                }
                for row in (await ses.execute(stmt)).mappings().all()
            ]
    return data


def _dump_snapshot(db_snapshot: SNAPSHOT) -> Path:
    logger.debug("DB dumping started")

    file_path = Path("data") / f"tracker_{_get_now()}.json"

    with file_path.open('w') as f:
        ujson.dump(db_snapshot, f, ensure_ascii=False, indent=2)

    logger.debug("DB dumped")

    return file_path


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
def drive_client():
    creds = _get_drive_creds()

    new_client = build('drive', 'v3', credentials=creds)
    try:
        yield new_client
    except Exception:
        logger.exception("Error with the client")
        raise


def _get_folder_id() -> str:
    with drive_client() as client:
        response = client.files().list(
            q="name = 'tracker'", spaces='drive', fields='files(id)').execute()
    return response['files'][0]['id']


def _send_dump(file_path: Path) -> None:
    logger.debug("Sending file %s", file_path)

    file_metadata = {
        'name': f"{file_path.name}",
        'parents': [_get_folder_id()]
    }
    file = MediaFileUpload(
        file_path, mimetype='application/json')

    with drive_client() as client:
        client.files().create(
            body=file_metadata, media_body=file).execute()
    logger.debug("File sent")


def _remove_file(file_path: Path) -> None:
    logger.debug("Removing '%s'", file_path)
    os.remove(file_path)
    logger.debug("File removed")


async def backup() -> None:
    logger.info("Backuping started")
    start_time = time.perf_counter()

    db_snapshot = await _get_db_snapshot()
    dump_file = _dump_snapshot(db_snapshot)
    _send_dump(dump_file)
    _remove_file(dump_file)

    logger.info("Backuping completed, %ss",
                round(time.perf_counter() - start_time, 2))


def _get_last_dump() -> str:
    logger.debug("Getting last dump started")
    folder_id = _get_folder_id()
    query = f"name contains 'tracker_' and mimeType='application/json' and '{folder_id}' in parents"

    with drive_client() as client:
        response = client.files().list(
            q=query, spaces='drive', fields='files(id,modifiedTime,name)')\
            .execute()
    files = response['files']
    files.sort(key=lambda resp: resp['modifiedTime'], reverse=True)

    logger.debug("%s files found", len(files))
    return files[0]['id']


def _download_file(file_id: str,
                   *,
                   filename: str = 'restore.json') -> Path:
    logger.debug("Downloading file id='%s'", file_id)
    path = Path('data') / filename

    with drive_client() as client:
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


@compiles(DropTable, "postgresql")
def _compile_drop_table(element, compiler, **kwargs):
    return compiler.visit_drop_table(element) + " CASCADE"


async def _recreate_db() -> None:
    async with database.engine.begin() as conn:
        await conn.run_sync(models.metadata.drop_all)
        await conn.run_sync(models.metadata.create_all)


def _convert_str_to_date(value: str) -> Any:
    try:
        return datetime.datetime.strptime(value, settings.DATETIME_FORMAT)
    except Exception:
        pass

    try:
        return datetime.datetime.strptime(value, settings.DATE_FORMAT).date()
    except Exception:
        pass

    return value


async def _restore_db(dump_path: Path) -> None:
    if not dump_path.exists():
        raise ValueError("Dump file not found")

    with dump_path.open() as f:
        data = ujson.load(f)

    async with database.session() as ses:
        # order of them matters
        for table in TABLES:
            values = [
                {
                    key: _convert_str_to_date(value)
                    for key, value in record.items()
                }
                for record in data[table.name]
            ]
            logger.debug("Inserting %s values to %s",
                         len(values), table.name)

            stmt = table.insert().values(values)
            await ses.execute(stmt)

            logger.debug("Data into %s inserted", table.name)


async def restore(*,
                  dump_path: Path | None = None) -> None:
    logger.info("Restoring started")
    start_time = time.perf_counter()

    dump_file_id = _get_last_dump()
    if not (dump_file_id or dump_path):
        raise ValueError("Dump not found")

    if dump_path:
        dump_file = Path('data') / dump_path
    else:
        dump_file = _download_file(dump_file_id)

    await _recreate_db()
    await _restore_db(dump_file)

    if dump_path is None:
        # don't remove local file
        _remove_file(dump_file)

    logger.info("Restoring completed, %ss",
                round(time.perf_counter() - start_time, 2))


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backup/restore the database"
    )
    parser.add_argument(
        '--backup',
        help="Create and send a backup to the Google Drive",
        action="store_true",
        dest="backup"
    )
    parser.add_argument(
        '--restore',
        help="Download the last backup from the Google Drive and restore the database",
        action="store_true",
        dest="restore"
    )
    parser.add_argument(
        '--restore-offline',
        help="Restore the database from the local file",
        type=Path,
        dest="restore_offline",
    )
    parser.add_argument(
        '--get-last-dump',
        help="Download the last backup from the Google Drive",
        action="store_true",
        dest="last_dump"
    )
    args = parser.parse_args()

    if args.backup:
        await backup()
    elif args.restore:
        await restore()
    elif args.last_dump:
        last_dump_id = _get_last_dump()
        _download_file(last_dump_id, filename='last_dump.json')
    elif dump_path := args.restore_offline:
        await restore(dump_path=dump_path)


if __name__ == "__main__":
    asyncio.run(main())
