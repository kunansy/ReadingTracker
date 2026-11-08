import importlib.util
import uuid
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest
import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy.engine import Connection

from tracker.common import database, sort_keys
from tracker.models import models


VERSIONS = Path(__file__).parents[1] / "migrations/alembic/versions"


def _load_migration(filename: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(filename, VERSIONS / filename)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MIGRATION = _load_migration("0003_chapter_length.py")
LATER_MIGRATIONS = (
    _load_migration("0005_drop_statuses.py"),
    _load_migration("0004_material_status_columns.py"),
)


def _downgrade_to_0003() -> None:
    for migration in LATER_MIGRATIONS:
        migration.downgrade()


async def _in_rolled_back_migration[T](check: Callable[[Connection], T]) -> T:
    async with database.engine.connect() as conn:
        trans = await conn.begin()
        try:

            def _run(sync_conn: Connection) -> T:
                with Operations.context(MigrationContext.configure(sync_conn)):
                    return check(sync_conn)

            return await conn.run_sync(_run)
        finally:
            await trans.rollback()


def _chapter_length(conn: Connection) -> int:
    return conn.scalar(
        sa.text(
            "SELECT character_maximum_length FROM information_schema.columns "
            "WHERE table_name = 'notes' AND column_name = 'chapter'",
        ),
    )


def _insert_note(conn: Connection, chapter: str) -> None:
    note_id = models.generate_id()
    material_id = uuid.uuid4()
    conn.execute(
        models.Notes.insert().values(
            note_id=note_id,
            material_id=str(material_id),
            content="Migration 0003 note",
            chapter=chapter,
            page=1,
            sort_key=sort_keys.note_sort_key(
                material_id=material_id,
                chapter=chapter,
                page=1,
                note_id=note_id,
            ),
        ),
    )


async def test_downgrade_restores_old_chapter_length():
    def check(conn: Connection) -> int:
        _downgrade_to_0003()
        MIGRATION.downgrade()
        return _chapter_length(conn)

    assert await _in_rolled_back_migration(check) == MIGRATION.OLD_CHAPTER_LENGTH


async def test_upgrade_refuses_chapters_over_the_limit():
    def check(conn: Connection) -> int:
        _downgrade_to_0003()
        MIGRATION.downgrade()
        _insert_note(conn, "1" * (MIGRATION.MAX_CHAPTER_LENGTH + 1))

        with pytest.raises(RuntimeError, match="1 notes have a chapter over 256"):
            MIGRATION.upgrade()
        return _chapter_length(conn)

    assert await _in_rolled_back_migration(check) == MIGRATION.OLD_CHAPTER_LENGTH


async def test_upgrade_keeps_chapters_at_the_limit():
    def check(conn: Connection) -> tuple[int, bool]:
        _downgrade_to_0003()
        MIGRATION.downgrade()
        _insert_note(conn, "1" * MIGRATION.MAX_CHAPTER_LENGTH)

        MIGRATION.upgrade()
        has_matview = conn.scalar(
            sa.text(
                "SELECT EXISTS "
                "(SELECT 1 FROM pg_matviews WHERE matviewname = 'mvw_repeat_notes')",
            ),
        )
        return _chapter_length(conn), has_matview

    length, has_matview = await _in_rolled_back_migration(check)

    assert length == MIGRATION.MAX_CHAPTER_LENGTH
    assert has_matview


def test_model_matches_migration_limit():
    assert MIGRATION.MAX_CHAPTER_LENGTH == models.MAX_CHAPTER_LENGTH
    assert models.Notes.c.chapter.type.length == models.MAX_CHAPTER_LENGTH
