"""migrations/alembic/env.py: the offline (SQL script) mode."""

import asyncio
import io

import pytest
from alembic import command

from tests.integration.migrations import helpers as migration_helpers


async def _offline_upgrade(revision: str) -> str:
    buffer = io.StringIO()
    config = migration_helpers.alembic_config(output_buffer=buffer)
    await asyncio.to_thread(command.upgrade, config, revision, sql=True)
    return buffer.getvalue()


async def test_offline_upgrade_emits_the_script_without_touching_the_database():
    script = await _offline_upgrade("0002")

    assert "CREATE TABLE alembic_version" in script
    assert "CREATE TABLE materials" in script
    assert "CREATE MATERIALIZED VIEW IF NOT EXISTS mvw_repeat_notes" in script
    assert "-- Running upgrade 0001 -> 0002" in script
    assert 'ALTER TABLE notes ADD COLUMN sort_key VARCHAR(512) COLLATE "C"' in script
    assert "UPDATE reading_log SET sort_key = material_id::text || '$$'" in script
    assert "UPDATE alembic_version SET version_num='0002' WHERE" in script
    assert script.rstrip().endswith("COMMIT;")
    assert await migration_helpers.current_revision() == migration_helpers.HEAD_REVISION


async def test_offline_upgrade_of_a_revision_range_emits_only_that_range():
    script = await _offline_upgrade("0001:0002")

    assert "CREATE TABLE materials" not in script
    assert "ALTER TABLE materials ADD COLUMN sort_key" in script


async def test_offline_upgrade_to_head_fails_at_0003_current_behaviour():
    # revisions 0003 and 0004 inspect the data through op.get_bind(), which has no database offline
    with pytest.raises(
        AttributeError,
        match="'MockConnection' object has no attribute 'scalar'",
    ):
        await _offline_upgrade("head")
