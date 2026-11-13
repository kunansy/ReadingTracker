import datetime
import uuid

import pytest
import sqlalchemy.sql as sa
from alembic import command
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.sql.ddl import DropTable

from tests.integration import (
    factories,
    helpers_notes as helpers,
)
from tracker.common import database, settings
from tracker.models import models


MATERIAL_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
ADDED_AT = datetime.datetime(2024, 1, 1)  # noqa: DTZ001


def _material_insert(material_id: uuid.UUID = MATERIAL_ID, **columns) -> sa.Insert:
    values = {
        "material_id": material_id,
        "title": f"Material {material_id}",
        "authors": "Author",
        "pages": 10,
        "material_type": "book",
        "added_at": ADDED_AT,
        "is_outlined": False,
        "sort_key": f"key-{material_id}",
        **columns,
    }
    return models.Materials.insert().values(values)


async def test_session_commits_so_another_session_sees_the_row():
    async with database.session() as ses:
        await ses.execute(_material_insert())

    async with database.session() as other:
        title = await other.scalar(
            sa.select(models.Materials.c.title).where(
                models.Materials.c.material_id == MATERIAL_ID,
            ),
        )

    assert title == f"Material {MATERIAL_ID}"


async def test_session_does_not_expose_uncommitted_rows():
    async with database.session() as ses:
        await ses.execute(_material_insert())

        async with database.session() as other:
            visible = await other.scalar(
                sa.select(sa.func.count()).select_from(models.Materials),
            )

    assert visible == 0
    assert await factories.count_rows(models.Materials) == 1


async def test_session_rolls_back_when_the_block_raises():
    with pytest.raises(database.DatabaseException):
        async with database.session() as ses:
            await ses.execute(_material_insert())
            raise RuntimeError("boom")

    assert await factories.count_rows(models.Materials) == 0


async def test_session_wraps_a_foreign_exception_current_behaviour():
    error = ValueError("not a database error")

    with pytest.raises(database.DatabaseException) as exc_info:
        async with database.session():
            raise error

    assert type(exc_info.value) is database.DatabaseException
    assert exc_info.value.args == (error,)
    assert exc_info.value.__cause__ is error


async def test_session_downgrades_a_not_found_raised_inside_it_current_behaviour():
    with pytest.raises(database.DatabaseException) as exc_info:
        async with database.session():
            raise database.NotFoundException("missing")

    # the subclass is lost: callers must raise NotFoundException after the block
    assert type(exc_info.value) is database.DatabaseException
    assert isinstance(exc_info.value.__cause__, database.NotFoundException)


async def test_session_turns_a_unique_violation_into_already_exists():
    await helpers.execute(_material_insert(title="Same", material_type="book"))

    with pytest.raises(database.AlreadyExistsException) as exc_info:
        async with database.session() as ses:
            await ses.execute(
                _material_insert(uuid.uuid4(), title="Same", material_type="book"),
            )

    assert "uix_material" in str(exc_info.value)
    assert exc_info.value.__cause__ is None
    assert await factories.count_rows(models.Materials) == 1


async def test_session_turns_another_integrity_error_into_a_database_exception():
    with pytest.raises(database.DatabaseException) as exc_info:
        async with database.session() as ses:
            await ses.execute(_material_insert(title=None))

    assert type(exc_info.value) is database.DatabaseException
    assert isinstance(exc_info.value.__cause__, IntegrityError)
    assert "NotNullViolationError" in str(exc_info.value)
    assert await factories.count_rows(models.Materials) == 0


async def test_session_turns_an_sql_error_into_a_database_exception():
    with pytest.raises(database.DatabaseException) as exc_info:
        async with database.session() as ses:
            await ses.execute(sa.text("SELECT * FROM no_such_table"))

    assert type(exc_info.value) is database.DatabaseException
    assert isinstance(exc_info.value.__cause__, DBAPIError)
    assert "no_such_table" in str(exc_info.value)


async def test_session_is_usable_again_after_an_error():
    with pytest.raises(database.DatabaseException):
        async with database.session() as ses:
            await ses.execute(sa.text("SELECT 1 / 0"))

    async with database.session() as ses:
        assert await ses.scalar(sa.text("SELECT 40 + 2")) == 42


async def test_transaction_commits_all_statements_together():
    async with database.transaction() as ses:
        await ses.execute(_material_insert())
        await ses.execute(_material_insert(uuid.uuid4()))

    assert await factories.count_rows(models.Materials) == 2


async def test_transaction_rolls_back_every_statement_on_an_error():
    with pytest.raises(database.AlreadyExistsException):
        async with database.transaction() as ses:
            await ses.execute(_material_insert(uuid.uuid4()))
            await ses.execute(_material_insert())
            await ses.execute(_material_insert())

    assert await factories.count_rows(models.Materials) == 0


async def test_transaction_rolls_back_when_the_block_raises():
    with pytest.raises(database.DatabaseException, match="boom"):
        async with database.transaction() as ses:
            await ses.execute(_material_insert())
            raise RuntimeError("boom")

    assert await factories.count_rows(models.Materials) == 0


async def test_json_columns_round_trip_through_the_engine_serializer():
    tags = ["тег", "emoji-🙂", 'quote"']
    note_id = await helpers.insert_raw_note(material_id=MATERIAL_ID, tags=tags)

    raw = await helpers.scalar(
        "SELECT tags::text FROM notes WHERE note_id = :id",
        id=note_id,
    )

    assert (await factories.fetch_row(models.Notes, note_id))["tags"] == tags
    assert raw == '["тег", "emoji-🙂", "quote\\""]'


async def test_check_inserted_one_accepts_a_single_row():
    async with database.session() as ses:
        result = await ses.execute(_material_insert())

    database.check_inserted_one(result, entity="Material")
    assert database.affected_rows(result) == 1


@pytest.mark.parametrize("rows", [0, 2], ids=["no-rows", "two-rows"])
async def test_check_inserted_one_rejects_any_other_row_count(rows):
    select = sa.select(
        sa.func.gen_random_uuid(),
        sa.literal(MATERIAL_ID),
        sa.literal(ADDED_AT),
    ).select_from(sa.func.generate_series(1, rows).alias("series"))
    stmt = models.Repeats.insert().from_select(
        ["repeat_id", "material_id", "repeated_at"],
        select,
    )

    async with database.session() as ses:
        result = await ses.execute(stmt)

    with pytest.raises(
        database.DatabaseException,
        match=f"Repeat insert affected {rows} rows",
    ):
        database.check_inserted_one(result, entity="Repeat")


async def test_check_updated_one_raises_not_found_when_nothing_matched():
    await helpers.execute(_material_insert())
    stmt = (
        models.Materials.update()
        .values(pages=1)
        .where(models.Materials.c.material_id == uuid.uuid4())
    )

    async with database.session() as ses:
        result = await ses.execute(stmt)

    with pytest.raises(
        database.NotFoundException,
        match="Material id='missing' not found",
    ):
        database.check_updated_one(result, entity="Material", entity_id="missing")


async def test_check_updated_one_accepts_a_single_row_and_rejects_two():
    await helpers.execute(_material_insert())
    await helpers.execute(_material_insert(uuid.uuid4()))
    one = (
        models.Materials.update()
        .values(pages=1)
        .where(
            models.Materials.c.material_id == MATERIAL_ID,
        )
    )
    both = models.Materials.update().values(pages=2)

    async with database.session() as ses:
        one_result = await ses.execute(one)
        both_result = await ses.execute(both)

    database.check_updated_one(one_result, entity="Material", entity_id=MATERIAL_ID)
    with pytest.raises(database.NotFoundException):
        database.check_updated_one(both_result, entity="Material", entity_id=MATERIAL_ID)


async def test_check_state_changed_raises_conflict_when_nothing_matched():
    await helpers.execute(_material_insert(started_at=ADDED_AT))
    stmt = (
        models.Materials.update()
        .values(started_at=ADDED_AT)
        .where(models.Materials.c.material_id == MATERIAL_ID)
        .where(models.MATERIAL_IS_QUEUED)
    )

    async with database.session() as ses:
        result = await ses.execute(stmt)

    with pytest.raises(database.ConflictException, match="already started"):
        database.check_state_changed(result, msg="already started")


async def test_check_state_changed_accepts_a_single_row():
    await helpers.execute(_material_insert())
    stmt = (
        models.Materials.update()
        .values(started_at=ADDED_AT)
        .where(models.Materials.c.material_id == MATERIAL_ID)
        .where(models.MATERIAL_IS_QUEUED)
    )

    async with database.session() as ses:
        result = await ses.execute(stmt)

    database.check_state_changed(result, msg="already started")
    assert (await factories.fetch_row(models.Materials, MATERIAL_ID))[
        "started_at"
    ] == ADDED_AT


async def test_readiness_is_true_on_a_live_database():
    assert await database.readiness() is True


async def test_readiness_is_false_when_the_database_is_unreachable(mocker):
    unreachable = create_async_engine(
        settings.DSN_TEMPLATE.format(
            username="tracker",
            password="tracker",
            host="127.0.0.1",
            port=1,
            db_name="tracker_test",
        ),
        connect_args={"timeout": 2},
    )
    mocker.patch.object(database, "engine", unreachable)

    try:
        assert await database.readiness() is False
    finally:
        await unreachable.dispose()


def test_drop_table_cascades_on_postgresql():
    ddl = str(DropTable(models.Notes).compile(dialect=postgresql.dialect()))

    assert ddl.strip() == "DROP TABLE notes CASCADE"


async def test_create_repeat_notes_matview_is_idempotent():
    async with database.session() as ses:
        await database.create_repeat_notes_matview(ses)
        await database.create_repeat_notes_matview(ses)

    assert (
        await helpers.scalar(
            "SELECT count(*) FROM pg_matviews WHERE matviewname = 'mvw_repeat_notes'",
        )
        == 1
    )


async def _is_matview_populated() -> bool:
    return await helpers.scalar(
        "SELECT ispopulated FROM pg_matviews WHERE matviewname = 'mvw_repeat_notes'",
    )


async def test_recreate_db_empties_every_table_and_restarts_the_sequences():
    material_id = await factories.start_material()
    note_id = await factories.insert_note(material_id=material_id)
    await factories.insert_note(material_id=material_id)
    await factories.insert_log(material_id=material_id)
    await factories.insert_card(material_id=material_id, note_id=note_id)
    await helpers.insert_repeat(material_id=material_id, repeated_at=ADDED_AT)
    await helpers.insert_note_repeat(note_id=note_id, repeated_at=ADDED_AT)
    schema_before = await helpers.schema_snapshot()

    try:
        await database.recreate_db()

        for table in models.metadata.sorted_tables:
            assert await factories.count_rows(table) == 0, table.name
        assert await helpers.schema_snapshot() == schema_before
        assert await helpers.current_revision() == helpers.HEAD_REVISION
        new_note_id = await factories.insert_note(material_id=material_id)
        assert (await factories.fetch_row(models.Notes, new_note_id))["note_number"] == 1
    finally:
        await helpers.reset_schema_to_head()


async def test_recreate_db_leaves_the_matview_unpopulated_current_behaviour():
    populated_before = await _is_matview_populated()

    try:
        await database.recreate_db()

        assert populated_before is True
        assert await _is_matview_populated() is False
        with pytest.raises(database.DatabaseException, match="has not been populated"):
            await helpers.fetch_all("SELECT * FROM mvw_repeat_notes")

        await factories.refresh_repeat_notes_matview()
        assert await helpers.fetch_all("SELECT * FROM mvw_repeat_notes") == []
    finally:
        await helpers.reset_schema_to_head()


async def test_reset_schema_to_head_restores_the_migrated_database():
    schema_before = await helpers.schema_snapshot()

    await helpers.reset_schema_to_head()

    assert await helpers.schema_snapshot() == schema_before
    assert await helpers.current_revision() == helpers.HEAD_REVISION
    assert await _is_matview_populated() is True


async def test_is_unversioned_db_is_false_for_a_migrated_database():
    assert await database._is_unversioned_db() is False


async def test_is_unversioned_db_is_true_without_the_alembic_version_table():
    try:
        await helpers.execute(sa.text("DROP TABLE alembic_version"))

        assert await database._is_unversioned_db() is True
    finally:
        await helpers.reset_schema_to_head()


async def test_is_unversioned_db_is_false_for_an_empty_database():
    try:
        await helpers.drop_everything()

        assert await database._is_unversioned_db() is False
    finally:
        await helpers.reset_schema_to_head()


async def test_create_db_on_an_empty_database_migrates_to_head_without_stamping(mocker):
    stamp = mocker.spy(command, "stamp")
    schema_before = await helpers.schema_snapshot()

    try:
        await helpers.drop_everything()

        await database.create_db()

        assert stamp.call_count == 0
        assert await helpers.current_revision() == helpers.HEAD_REVISION
        assert await helpers.schema_snapshot() == schema_before
    finally:
        await helpers.reset_schema_to_head()


async def test_create_db_on_a_migrated_database_changes_nothing(mocker):
    stamp = mocker.spy(command, "stamp")
    material_id = await factories.insert_material(title="Survivor")

    await database.create_db()

    assert stamp.call_count == 0
    assert await helpers.current_revision() == helpers.HEAD_REVISION
    assert (await factories.fetch_row(models.Materials, material_id))[
        "title"
    ] == "Survivor"


async def test_create_db_stamps_a_pre_alembic_database_and_upgrades_it(mocker):
    stamp = mocker.spy(command, "stamp")
    note_id = uuid.uuid4()

    try:
        await helpers.alembic_downgrade("0001")
        await helpers.execute(sa.text("DROP TABLE alembic_version"))
        await helpers.execute(
            sa.text(
                "INSERT INTO materials (material_id, title, authors, pages, material_type, "
                "added_at, is_outlined) "
                "VALUES (:id, 'Old', 'Author', 10, 'book', :added_at, false)",
            ),
            {"id": MATERIAL_ID, "added_at": ADDED_AT},
        )
        await helpers.execute(
            sa.text(
                "INSERT INTO statuses (status_id, material_id, started_at) "
                "VALUES (gen_random_uuid(), :id, :started_at)",
            ),
            {"id": MATERIAL_ID, "started_at": ADDED_AT},
        )
        await helpers.execute(
            sa.text(
                "INSERT INTO notes (note_id, material_id, content, added_at, chapter, page, "
                "tags, is_deleted) VALUES (:id, :material_id, 'Old note', :added_at, "
                "'Ch 3', 7, '[]', false)",
            ),
            {"id": note_id, "material_id": MATERIAL_ID, "added_at": ADDED_AT},
        )
        await database.engine.dispose()

        await database.create_db()
        await database.engine.dispose()

        assert stamp.call_count == 1
        assert stamp.call_args.args[1] == "0001"
        assert await helpers.current_revision() == helpers.HEAD_REVISION
        material = await factories.fetch_row(models.Materials, MATERIAL_ID)
        assert material["started_at"] == ADDED_AT
        assert material["completed_at"] is None
        assert material["sort_key"] == f"2024-01-01T00:00:00.000000$${MATERIAL_ID}"
        note = await factories.fetch_row(models.Notes, note_id)
        assert note["sort_key"] == f"{MATERIAL_ID}$$0000000003$$0000000007$${note_id}"
    finally:
        await helpers.reset_schema_to_head()


async def test_create_db_fails_on_tables_made_by_create_all_current_behaviour():
    try:
        await database.recreate_db()
        await helpers.execute(sa.text("DROP TABLE alembic_version"))
        await database.engine.dispose()

        # stamped as 0001, although metadata.create_all built the head schema
        with pytest.raises(
            DBAPIError,
            match='column "sort_key" of relation "materials" already',
        ):
            await database.create_db()

        assert await helpers.current_revision() == "0001"
    finally:
        await helpers.reset_schema_to_head()


def test_utcnow_is_naive_and_utc_today_is_its_date(mocker):
    now = database.utcnow()
    mocker.patch.object(database, "utcnow", return_value=helpers.FROZEN_NOW)

    assert now.tzinfo is None
    assert database.utc_today() == helpers.FROZEN_TODAY
