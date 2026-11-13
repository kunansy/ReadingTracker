import datetime
from collections.abc import Callable
from typing import Any
from uuid import UUID

import pytest

from tracker.notes import db


MATERIAL_ID = UUID(int=1000)
OTHER_MATERIAL_ID = UUID(int=2000)


def note_id(number: int) -> UUID:
    return UUID(int=number)


def build_note(number: int, *, link: int | None = None, **fields: Any) -> db.Note:
    values = {
        "note_id": note_id(number),
        "link_id": note_id(link) if link is not None else None,
        "material_id": MATERIAL_ID,
        "content": f"note {number}",
        "added_at": datetime.datetime(2024, 1, 2, 3, 4, 5),  # noqa: DTZ001
        "chapter": "1",
        "page": 1,
        "tags": set(),
        "is_deleted": False,
        "note_number": number,
    }
    return db.Note(**(values | fields))


def by_id(*notes: db.Note) -> dict[UUID, db.Note]:
    return {note.note_id: note for note in notes}


@pytest.fixture
def make_note() -> Callable[..., db.Note]:
    return build_note


class FakeResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return self._rows


class FakeSession:
    """Records executed statements instead of sending them to a database."""

    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows
        self.statements: list[Any] = []

    async def execute(self, stmt: Any) -> FakeResult:
        self.statements.append(stmt)
        return FakeResult(self._rows)
