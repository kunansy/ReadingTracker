#!/usr/bin/env python3
import argparse
import asyncio
from pathlib import Path

from tracker.google_drive import db, drive_api


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backup/restore the database")
    parser.add_argument(
        "--backup",
        help="Create and send a backup to the Google Drive",
        action="store_true",
        dest="backup",
    )
    parser.add_argument(
        "--restore",
        help="Download the last backup from the Google Drive and restore the database",
        action="store_true",
        dest="restore",
    )
    parser.add_argument(
        "--backup-offline",
        help="Dump the database to the local file",
        action="store_true",
        dest="backup_offline",
    )
    parser.add_argument(
        "--restore-offline",
        help="Restore the database from the local file",
        type=Path,
        dest="restore_offline",
    )
    parser.add_argument(
        "--get-last-dump",
        help="Download the last backup from the Google Drive",
        action="store_true",
        dest="get_last_dump",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    if args.backup:
        raise NotImplementedError
    elif args.restore:
        await drive_api.restore()
    elif args.get_last_dump:
        dump = await drive_api.get_dump()
        filepath = db.get_dump_filename(prefix="last_dump")
        drive_api.dump_json(dump, filepath=filepath)
    elif dump_path := args.restore_offline:
        await drive_api.restore(dump_path=dump_path)
    elif args.backup_offline:
        raise NotImplementedError


if __name__ == "__main__":
    asyncio.run(main())
