import datetime
import importlib.util
import uuid
from pathlib import Path
from types import ModuleType

import pytest
import sqlalchemy.sql as sa

from tracker.common import database, sort_keys


MIGRATION = Path(__file__).parents[1] / "migrations/alembic/versions/0002_sort_key.py"


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("migration_0002", MIGRATION)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BACKFILL: dict[str, str] = _load_migration().BACKFILL


async def _backfill(table: str, columns: str, **params: object) -> str:
    query = sa.text(f"SELECT {BACKFILL[table]} FROM (SELECT {columns}) AS t")  # noqa: S608
    async with database.session() as ses:
        return await ses.scalar(query, params)


@pytest.mark.parametrize(
    "added_at",
    [
        datetime.datetime(2024, 1, 2, 3, 4, 5),  # noqa: DTZ001
        datetime.datetime(2024, 1, 2, 3, 4, 5, 6),  # noqa: DTZ001
    ],
)
async def test_materials_backfill_matches_python(added_at):
    material_id = uuid.uuid4()

    result = await _backfill(
        "materials",
        "CAST(:added_at AS timestamp) AS added_at, CAST(:id AS uuid) AS material_id",
        added_at=added_at,
        id=str(material_id),
    )

    assert result == sort_keys.material_sort_key(added_at=added_at, material_id=material_id)


async def test_cards_backfill_matches_python():
    added_at = datetime.datetime(2024, 1, 2, 3, 4, 5, 999_999)  # noqa: DTZ001
    card_id = uuid.uuid4()

    result = await _backfill(
        "cards",
        "CAST(:added_at AS timestamp) AS added_at, CAST(:id AS uuid) AS card_id",
        added_at=added_at,
        id=str(card_id),
    )

    assert result == sort_keys.card_sort_key(added_at=added_at, card_id=card_id)


async def test_reading_log_backfill_matches_python():
    material_id, log_id = uuid.uuid4(), uuid.uuid4()
    date = datetime.date(2024, 1, 2)

    result = await _backfill(
        "reading_log",
        "CAST(:material_id AS uuid) AS material_id, CAST(:date AS date) AS date,"
        " CAST(:log_id AS uuid) AS log_id",
        material_id=str(material_id),
        date=date,
        log_id=str(log_id),
    )

    assert result == sort_keys.reading_log_sort_key(
        material_id=material_id,
        date=date,
        log_id=log_id,
    )


@pytest.mark.parametrize(
    ("chapter", "page"),
    [
        (None, 0),
        ("", 1),
        ("abc", 2),
        ("007", 3),
        ("Глава 12", 4),
        ("1.2", 5),
        ("12345678901", 6),
        ("1", 2_147_483_647),
    ],
)
async def test_notes_backfill_matches_python(chapter, page):
    material_id, note_id = uuid.uuid4(), uuid.uuid4()

    result = await _backfill(
        "notes",
        "CAST(:material_id AS uuid) AS material_id, CAST(:chapter AS text) AS chapter,"
        " CAST(:page AS integer) AS page, CAST(:note_id AS uuid) AS note_id",
        material_id=str(material_id),
        chapter=chapter,
        page=page,
        note_id=str(note_id),
    )

    assert result == sort_keys.note_sort_key(
        material_id=material_id,
        chapter=chapter,
        page=page,
        note_id=note_id,
    )
