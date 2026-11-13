from typing import Any
from uuid import UUID

from tests.unit.helpers import make_note
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
        "note_number": number,
    }
    return make_note(**(values | fields))


def by_id(*notes: db.Note) -> dict[UUID, db.Note]:
    return {note.note_id: note for note in notes}


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
