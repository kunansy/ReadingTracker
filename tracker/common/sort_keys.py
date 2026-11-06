"""Sort keys for keyset pagination.

Every key is a string that sorts (with the "C" collation) in listing order
and ends with the row id, so keys are unique. The SQL backfill in
migrations/alembic/versions/0002_sort_key.py must produce identical values.
"""

import datetime
import string
from typing import Final
from uuid import UUID


SEPARATOR: Final[str] = "$$"
DATETIME_FORMAT: Final[str] = "%Y-%m-%dT%H:%M:%S.%f"
DATE_FORMAT: Final[str] = "%Y-%m-%d"
INT_WIDTH: Final[int] = 10


def join(*parts: str) -> str:
    return SEPARATOR.join(parts)


def pad_int(value: int | str) -> str:
    # zfill never truncates, unlike SQL lpad; the SQL side guards it the same way
    return str(value).zfill(INT_WIDTH)


def chapter_digits(chapter: str | None) -> str:
    digits = "".join(symb for symb in chapter or "" if symb in string.digits)
    return digits.lstrip("0") or "0"


def chapter_int(chapter: str | None) -> int:
    return int(chapter_digits(chapter))


def material_sort_key(*, added_at: datetime.datetime, material_id: UUID | str) -> str:
    return join(added_at.strftime(DATETIME_FORMAT), str(material_id))


def reading_log_sort_key(*, date: datetime.date, log_id: UUID | str) -> str:
    return join(date.strftime(DATE_FORMAT), str(log_id))


def card_sort_key(*, added_at: datetime.datetime, card_id: UUID | str) -> str:
    return join(added_at.strftime(DATETIME_FORMAT), str(card_id))


def note_sort_key(
    *,
    material_id: UUID | str,
    chapter: str | None,
    page: int,
    note_id: UUID | str,
) -> str:
    return join(
        str(material_id),
        pad_int(chapter_digits(chapter)),
        pad_int(page),
        str(note_id),
    )
