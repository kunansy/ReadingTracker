#!/usr/bin/env python3
import argparse
import asyncio
import contextlib
import datetime
import io
import os
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, NamedTuple

import sqlalchemy.sql as sa
import ujson
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.ddl import DropTable, CreateTable
from sqlalchemy.sql.schema import Table

from tracker.common import database, models, settings
from tracker.common.log import logger


class TableSnapshot(NamedTuple):
    table_name: str
    rows: list[dict[str, str]]

    @property
    def counter(self) -> int:
        return len(self.rows)


class DBSnapshot(NamedTuple):
    tables: list[TableSnapshot]


DUMP_DATA = dict[str, list[dict[str, str]]]

SCOPES = ['https://www.googleapis.com/auth/drive']
TABLES = {
    models.Materials.name: models.Materials,
    models.Statuses.name: models.Statuses,
    models.ReadingLog.name: models.ReadingLog,
    models.Notes.name: models.Notes,
    models.Cards.name: models.Cards,
}


def _get_now() -> str:
    now = datetime.datetime.utcnow()
    return now.strftime(settings.DATETIME_FORMAT).replace(' ', '_')


def _convert_date_to_str(value: Any) -> Any:
    if isinstance(value, datetime.date):
        return value.strftime(settings.DATE_FORMAT)
    if isinstance(value, datetime.datetime):
        return value.strftime(settings.DATETIME_FORMAT)
    return value


async def _get_table_snapshot(*,
                              table: Table,
                              conn: AsyncSession) -> TableSnapshot:
    stmt = sa.select(table)
    rows = [
        {
            str(key): _convert_date_to_str(value)
            for key, value in row.items()
        }
        for row in (await conn.execute(stmt)).mappings().all()
    ]
    return TableSnapshot(
        table_name=table.name,
        rows=rows
    )


async def _get_db_snapshot() -> DBSnapshot:
    table_snapshots = []
    async with database.transaction() as ses:
        for table in TABLES.values():
            table_snapshot = await _get_table_snapshot(table=table, conn=ses)
            table_snapshots += [table_snapshot]

            logger.debug("%s: %s rows got", table.name, table_snapshot.counter)

    return DBSnapshot(tables=table_snapshots)


def _dump_snapshot(snapshot: DBSnapshot) -> Path:
    logger.debug("DB dumping started")

    file_path = Path("data") / f"tracker_{_get_now()}.json"

    data = {
        table_snapshot.table_name: table_snapshot.rows
        for table_snapshot in snapshot.tables
    }
    with file_path.open('w') as f:
        ujson.dump(data, f, ensure_ascii=False, indent=2)

    logger.debug("DB dumped")

    return file_path


@lru_cache
def _get_drive_creds() -> Credentials:
    creds = None
    if settings.DRIVE_TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(
            settings.DRIVE_TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
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


async def backup() -> DBSnapshot:
    logger.info("Backuping started")
    start_time = time.perf_counter()

    db_snapshot = await _get_db_snapshot()
    dump_file = _dump_snapshot(db_snapshot)
    _send_dump(dump_file)
    _remove_file(dump_file)

    logger.info("Backuping completed, %ss",
                round(time.perf_counter() - start_time, 2))

    return db_snapshot


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


async def _drop_tables(conn: AsyncSession) -> None:
    for table in TABLES.values():
        await conn.execute(DropTable(table))


async def _create_tables(conn: AsyncSession) -> None:
    for table in TABLES.values():
        await conn.execute(CreateTable(table))


async def _recreate_db(conn: AsyncSession) -> None:
    await _drop_tables(conn)
    await _create_tables(conn)


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


def _read_json_file(filepath: Path) -> dict[str, Any]:
    assert filepath.exists(), "File not found"
    assert filepath.suffix == '.json', "File must be json"

    with filepath.open() as f:
        return ujson.load(f)


def _convert_dump_to_snapshot(dump_data: DUMP_DATA) -> DBSnapshot:
    tables = []
    for table_name, values in dump_data.items():
        rows = [
            {
                key: _convert_str_to_date(value)
                for key, value in row.items()
            }
            for row in values
        ]
        tables += [
            TableSnapshot(
                table_name=table_name,
                rows=rows
            )
        ]

    return DBSnapshot(tables=tables)


async def _restore_db(*,
                      dump_path: Path,
                      conn: AsyncSession) -> DBSnapshot:
    if not dump_path.exists():
        raise ValueError("Dump file not found")

    dump_data = _read_json_file(dump_path)
    snapshot = _convert_dump_to_snapshot(dump_data)
    snapshot_dict = {
        table.table_name: table.rows
        for table in snapshot.tables
    }

    # order of them matters
    for table_name, table in TABLES.items():
        values = snapshot_dict[table_name]
        stmt = table.insert().values(values)
        await conn.execute(stmt)

        logger.debug("%s: %s rows inserted",
                     table.name, len(snapshot_dict[table_name]))
    return snapshot


async def restore(*,
                  dump_path: Path | None = None) -> DBSnapshot:
    logger.info("Restoring started")
    start_time = time.perf_counter()

    async with database.transaction() as ses:
        if dump_path:
            if 'data/' not in str(dump_path):
                dump_path = Path('data') / dump_path

            assert dump_path.exists(), f"File {dump_path=} not found"

            await _recreate_db(conn=ses)
            snapshot = await _restore_db(conn=ses, dump_path=dump_path)

            logger.info("Restoring completed, %ss",
                        round(time.perf_counter() - start_time, 2))
            return snapshot

        if not (dump_file_id := _get_last_dump()):
            raise ValueError("Dump not found")

        dump_file = _download_file(dump_file_id)

        await _recreate_db(conn=ses)
        snapshot = await _restore_db(conn=ses, dump_path=dump_file)

        _remove_file(dump_file)

        logger.info("Restoring completed, %ss",
                    round(time.perf_counter() - start_time, 2))
    return snapshot


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
        '--backup-offline',
        help="Dump the database to the local file",
        action="store_true",
        dest="backup_offline",
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
    elif args.backup_offline:
        snapshot = await _get_db_snapshot()
        _dump_snapshot(snapshot)


if __name__ == "__main__":
    asyncio.run(main())
