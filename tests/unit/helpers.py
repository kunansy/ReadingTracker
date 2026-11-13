"""Clock, id, SQL and model helpers shared by the unit suites."""

import datetime
from typing import Any
from uuid import UUID

import sqlalchemy.sql as sa
from sqlalchemy.dialects import postgresql

from tracker.materials import db as materials_db
from tracker.models import enums
from tracker.notes import db as notes_db


NOW = datetime.datetime(2024, 3, 10, 12, 30, 45)
TODAY = NOW.date()


def uid(number: int) -> UUID:
    return UUID(int=number)


def day(offset: int) -> datetime.date:
    """The date `offset` days away from the frozen today."""
    return TODAY + datetime.timedelta(days=offset)


def midnight(offset: int) -> datetime.datetime:
    return datetime.datetime.combine(day(offset), datetime.time())


def compile_sql(stmt: sa.ClauseElement) -> str:
    compiled = stmt.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True},
    )
    return " ".join(str(compiled).split())


def make_material(**overrides: Any) -> materials_db.Material:
    fields: dict[str, Any] = {
        "material_id": uid(1),
        "title": "Преступление и наказание",
        "authors": "Достоевский",
        "pages": 100,
        "material_type": enums.MaterialTypesEnum.book,
        "tags": None,
        "link": None,
        "added_at": datetime.datetime(2024, 1, 1, 8, 0),
        "is_outlined": False,
        "started_at": None,
        "completed_at": None,
    }
    return materials_db.Material(**(fields | overrides))


def make_note(**overrides: Any) -> notes_db.Note:
    fields: dict[str, Any] = {
        "note_id": uid(1),
        "link_id": None,
        "material_id": uid(1000),
        "content": "note 1",
        "added_at": datetime.datetime(2024, 1, 2, 3, 4, 5),
        "chapter": "1",
        "page": 1,
        "tags": set(),
        "is_deleted": False,
        "note_number": 1,
    }
    return notes_db.Note(**(fields | overrides))
