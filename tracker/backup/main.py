#!/usr/bin/env python3
import argparse
import asyncio

from tracker.backup import client


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backup/restore the database via the fastbackup service",
    )
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--backup", help="Create a backup", action="store_true")
    actions.add_argument(
        "--restore",
        help="Restore the database from the latest backup",
        action="store_true",
    )
    actions.add_argument(
        "--get-last-dump",
        help="Download the latest backup: .pgdump, or .json for legacy backups",
        action="store_true",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    if args.backup:
        await client.backup()
    elif args.restore:
        await client.restore()
    else:
        await client.download_latest()


if __name__ == "__main__":
    asyncio.run(main())
