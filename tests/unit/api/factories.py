import datetime
from typing import Any
from uuid import UUID

from tracker.cards import db as cards_db
from tracker.common import database, pagination
from tracker.materials import db as materials_db
from tracker.models import enums
from tracker.notes import db as notes_db
from tracker.reading_log import db as reading_log_db


MATERIAL_ID = UUID("11111111-1111-4111-8111-111111111111")
OTHER_MATERIAL_ID = UUID("22222222-2222-4222-8222-222222222222")
NOTE_ID = UUID("33333333-3333-4333-8333-333333333333")
OTHER_NOTE_ID = UUID("44444444-4444-4444-8444-444444444444")
CARD_ID = UUID("55555555-5555-4555-8555-555555555555")
LOG_ID = UUID("66666666-6666-4666-8666-666666666666")
ADDED_AT = datetime.datetime(2026, 1, 2, 3, 4, 5)
TODAY = datetime.date(2026, 3, 10)


def page(
    items: list[Any] | None = None, *, next_token: str | None = None
) -> pagination.Page:
    items = items or []
    return pagination.Page(items=items, next_token=next_token, total_count=len(items))


def note(**fields: Any) -> notes_db.Note:
    defaults: dict[str, Any] = {
        "note_id": NOTE_ID,
        "material_id": MATERIAL_ID,
        "content": "Content #tag",
        "added_at": ADDED_AT,
        "chapter": "3",
        "page": 10,
        "tags": {"tag"},
        "is_deleted": False,
        "note_number": 7,
    }
    return notes_db.Note(**{**defaults, **fields})


def note_json(**fields: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "note_id": str(NOTE_ID),
        "link_id": None,
        "material_id": str(MATERIAL_ID),
        "title": None,
        "content": "Content #tag",
        "added_at": "2026-01-02 03:04:05",
        "chapter": "3",
        "page": 10,
        "tags": ["tag"],
        "is_deleted": False,
        "note_number": 7,
        "links_count": None,
    }
    return {**defaults, **fields}


def material(**fields: Any) -> materials_db.Material:
    defaults: dict[str, Any] = {
        "material_id": MATERIAL_ID,
        "title": "Война и мир",
        "authors": "Лев Толстой",
        "pages": 1300,
        "material_type": enums.MaterialTypesEnum.book,
        "tags": "classic, russian",
        "link": None,
        "added_at": ADDED_AT,
        "is_outlined": False,
    }
    return materials_db.Material(**{**defaults, **fields})


def material_json(**fields: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "material_id": str(MATERIAL_ID),
        "title": "Война и мир",
        "authors": "Лев Толстой",
        "pages": 1300,
        "material_type": "book",
        "tags": "classic, russian",
        "link": None,
        "added_at": "2026-01-02T03:04:05",
        "is_outlined": False,
    }
    return {**defaults, **fields}


def material_statistics(**fields: Any) -> materials_db.MaterialStatistics:
    defaults: dict[str, Any] = {
        "material": material(),
        "started_at": datetime.date(2026, 1, 10),
        "duration": 20,
        "lost_time": 5,
        "total": 650,
        "min_record": None,
        "max_record": database.MinMax(
            log_id=LOG_ID,
            material_id=MATERIAL_ID,
            material_title="Война и мир",
            count=90,
            date=datetime.date(2026, 1, 15),
        ),
        "mean": 33,
        "notes_count": 4,
    }
    return materials_db.MaterialStatistics(**{**defaults, **fields})


def material_statistics_json(**fields: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "material": material_json(),
        "started_at": "2026-01-10",
        "duration": 20,
        "lost_time": 5,
        "total": 650,
        "min_record": None,
        "max_record": {
            "log_id": str(LOG_ID),
            "material_id": str(MATERIAL_ID),
            "material_title": "Война и мир",
            "count": 90,
            "date": "2026-01-15",
        },
        "mean": 33,
        "notes_count": 4,
        "remaining_pages": None,
        "remaining_days": None,
        "completed_at": None,
        "total_reading_duration": None,
        "would_be_completed": None,
        "percent_completed": 50.0,
    }
    return {**defaults, **fields}


def card(**fields: Any) -> cards_db.Card:
    defaults: dict[str, Any] = {
        "card_id": CARD_ID,
        "note_id": NOTE_ID,
        "material_id": MATERIAL_ID,
        "question": "Кто автор?",
        "answer": None,
        "added_at": ADDED_AT,
        "note_title": None,
        "note_content": "Content",
        "note_chapter": "",
        "note_page": 0,
        "material_title": "Война и мир",
        "material_authors": "Лев Толстой",
        "material_type": enums.MaterialTypesEnum.book,
    }
    return cards_db.Card(**{**defaults, **fields})


def card_json(**fields: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "card_id": str(CARD_ID),
        "note_id": str(NOTE_ID),
        "material_id": str(MATERIAL_ID),
        "question": "Кто автор?",
        "answer": None,
        "added_at": "2026-01-02T03:04:05",
        "note_title": None,
        "note_content": "Content",
        "note_chapter": "",
        "note_page": 0,
        "material_title": "Война и мир",
        "material_authors": "Лев Толстой",
        "material_type": "book",
    }
    return {**defaults, **fields}


def log_record(**fields: Any) -> reading_log_db.LogRecord:
    defaults: dict[str, Any] = {
        "log_id": LOG_ID,
        "date": datetime.date(2026, 1, 15),
        "count": 90,
        "material_id": MATERIAL_ID,
        "material_title": "Война и мир",
    }
    return reading_log_db.LogRecord(**{**defaults, **fields})
