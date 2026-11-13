import sqlalchemy.sql as sa

from tests.integration import factories
from tracker.common import database, settings
from tracker.models import models


async def test_database_is_the_throwaway_container_at_head():
    async with database.session() as ses:
        db_name = await ses.scalar(sa.text("SELECT current_database()"))
        version = await ses.scalar(sa.text("SELECT version_num FROM alembic_version"))

    assert db_name == "tracker_test"
    assert settings.DB_URI.endswith("/tracker_test")
    assert version == "0007"


async def test_factories_write_rows_the_test_reads_back():
    material_id = await factories.start_material(title="Read my writes")
    note_id = await factories.insert_note(material_id=material_id, tags=["tag"])
    await factories.insert_log(material_id=material_id, count=7)
    await factories.insert_card(material_id=material_id, note_id=note_id)

    material = await factories.fetch_row(models.Materials, material_id)

    assert material["title"] == "Read my writes"
    assert await factories.count_rows(models.ReadingLog) == 1
    assert await factories.count_rows(models.Cards) == 1


async def test_tables_are_empty_at_the_start_of_every_test():
    for table in models.metadata.sorted_tables:
        assert await factories.count_rows(table) == 0, table.name
