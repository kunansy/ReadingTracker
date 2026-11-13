import datetime
import importlib.util
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql.ddl import DropTable

from tracker.common import database, settings
from tracker.models import models


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class _FakeSession:
    def __init__(self, mocker, *, commit_error: Exception | None = None) -> None:
        self.commit = mocker.AsyncMock(side_effect=commit_error)
        self.rollback = mocker.AsyncMock()
        self.close = mocker.AsyncMock()
        self.begin_events: list[str] = []

    @asynccontextmanager
    async def _begin(self):
        self.begin_events.append("enter")
        try:
            yield
        finally:
            self.begin_events.append("exit")

    def begin(self):
        return self._begin()


@pytest.fixture
def fake_session(mocker) -> _FakeSession:
    ses = _FakeSession(mocker)
    mocker.patch.object(database, "AsyncSession", return_value=ses)
    return ses


def _integrity_error(pgcode: str | None, *args: str) -> IntegrityError:
    orig = Exception(*args)
    if pgcode is not None:
        orig.pgcode = pgcode
    return IntegrityError("INSERT", {}, orig)


class _FixedDatetime(datetime.datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2024, 2, 29, 23, 59, 59, 123456, tzinfo=tz)


@pytest.fixture
def frozen_clock(mocker):
    fake_module = SimpleNamespace(datetime=_FixedDatetime, UTC=datetime.UTC)
    mocker.patch.object(database, "datetime", fake_module)


def test_utcnow_is_naive_utc(frozen_clock):
    result = database.utcnow()

    assert result == datetime.datetime(2024, 2, 29, 23, 59, 59, 123456)
    assert result.tzinfo is None


def test_utcnow_asks_the_clock_for_utc(mocker):
    clock = mocker.Mock()
    clock.now.return_value = datetime.datetime(
        2024,
        1,
        1,
        3,
        tzinfo=datetime.timezone(datetime.timedelta(hours=3)),
    )
    mocker.patch.object(
        database,
        "datetime",
        SimpleNamespace(datetime=clock, UTC=datetime.UTC),
    )

    database.utcnow()

    clock.now.assert_called_once_with(datetime.UTC)


def test_utc_today_is_the_date_of_utcnow(mocker):
    mocker.patch.object(
        database,
        "utcnow",
        return_value=datetime.datetime(2024, 12, 31, 23, 59, 59, 999_999),
    )

    assert database.utc_today() == datetime.date(2024, 12, 31)


def test_exception_hierarchy():
    for exception in (
        database.AlreadyExistsException,
        database.NotFoundException,
        database.ConflictException,
        database.InvalidNextTokenException,
    ):
        assert issubclass(exception, database.DatabaseException)


@pytest.mark.parametrize("rowcount", [0, 1, 2, -1], ids=["zero", "one", "two", "unknown"])
def test_affected_rows_returns_rowcount(rowcount):
    assert database.affected_rows(SimpleNamespace(rowcount=rowcount)) == rowcount


def test_check_inserted_one_passes_for_one_row():
    assert database.check_inserted_one(SimpleNamespace(rowcount=1), entity="Card") is None


@pytest.mark.parametrize("rowcount", [0, 2, -1], ids=["zero", "two", "unknown"])
def test_check_inserted_one_raises_for_other_row_counts(rowcount):
    with pytest.raises(database.DatabaseException) as exc_info:
        database.check_inserted_one(SimpleNamespace(rowcount=rowcount), entity="Card")

    assert str(exc_info.value) == f"Card insert affected {rowcount} rows, expected 1"
    assert type(exc_info.value) is database.DatabaseException


def test_check_updated_one_passes_for_one_row():
    result = SimpleNamespace(rowcount=1)

    assert database.check_updated_one(result, entity="Note", entity_id=1) is None


@pytest.mark.parametrize("rowcount", [0, 2], ids=["zero", "two"])
def test_check_updated_one_raises_not_found_for_other_row_counts(rowcount):
    entity_id = UUID("018e9dbe-1d3d-7a5a-b437-9bfa65171b42")

    with pytest.raises(database.NotFoundException) as exc_info:
        database.check_updated_one(
            SimpleNamespace(rowcount=rowcount),
            entity="Note",
            entity_id=entity_id,
        )

    assert str(exc_info.value) == (
        "Note id=UUID('018e9dbe-1d3d-7a5a-b437-9bfa65171b42') not found"
    )


def test_check_state_changed_passes_for_one_row():
    assert database.check_state_changed(SimpleNamespace(rowcount=1), msg="x") is None


@pytest.mark.parametrize("rowcount", [0, 2], ids=["zero", "two"])
def test_check_state_changed_raises_conflict_for_other_row_counts(rowcount):
    with pytest.raises(database.ConflictException) as exc_info:
        database.check_state_changed(
            SimpleNamespace(rowcount=rowcount),
            msg="Material is not in the queue",
        )

    assert str(exc_info.value) == "Material is not in the queue"


async def test_session_is_bound_to_engine_and_gets_kwargs(mocker, real_database_api):
    ses = _FakeSession(mocker)
    session_class = mocker.patch.object(database, "AsyncSession", return_value=ses)

    async with real_database_api.session(expire_on_commit=False) as opened:
        assert opened is ses

    session_class.assert_called_once_with(expire_on_commit=False, bind=database.engine)


async def test_session_commits_and_closes_on_success(fake_session, real_database_api):
    async with real_database_api.session():
        fake_session.commit.assert_not_awaited()

    fake_session.commit.assert_awaited_once_with()
    fake_session.rollback.assert_not_awaited()
    fake_session.close.assert_awaited_once_with()


async def test_session_turns_unique_violation_into_already_exists(
    fake_session,
    real_database_api,
):
    error = _integrity_error("23505", "duplicate key value", "uix_material")

    with pytest.raises(database.AlreadyExistsException) as exc_info:
        async with real_database_api.session():
            raise error

    assert exc_info.value.args == (("duplicate key value", "uix_material"),)
    assert exc_info.value.__cause__ is None
    fake_session.commit.assert_not_awaited()
    fake_session.close.assert_awaited_once_with()


async def test_session_does_not_roll_back_unique_violation_current_behaviour(
    fake_session,
    real_database_api,
):
    with pytest.raises(database.AlreadyExistsException):
        async with real_database_api.session():
            raise _integrity_error("23505")

    fake_session.rollback.assert_not_awaited()


async def test_session_turns_unique_violation_on_commit_into_already_exists(
    mocker,
    real_database_api,
):
    ses = _FakeSession(mocker, commit_error=_integrity_error("23505", "deferred"))
    mocker.patch.object(database, "AsyncSession", return_value=ses)

    with pytest.raises(database.AlreadyExistsException):
        async with real_database_api.session():
            pass

    ses.close.assert_awaited_once_with()


@pytest.mark.parametrize(
    "pgcode", ["23503", "23502", None], ids=["fk", "not-null", "none"]
)
async def test_session_rolls_back_other_integrity_errors(
    fake_session,
    real_database_api,
    pgcode,
):
    error = _integrity_error(pgcode, "violation")

    with pytest.raises(database.DatabaseException) as exc_info:
        async with real_database_api.session():
            raise error

    assert type(exc_info.value) is database.DatabaseException
    assert exc_info.value.args == (error,)
    assert exc_info.value.__cause__ is error
    fake_session.commit.assert_not_awaited()
    fake_session.rollback.assert_awaited_once_with()
    fake_session.close.assert_awaited_once_with()


async def test_session_rolls_back_and_wraps_any_other_error(
    fake_session,
    real_database_api,
):
    error = RuntimeError("connection lost")

    with pytest.raises(database.DatabaseException) as exc_info:
        async with real_database_api.session():
            raise error

    assert type(exc_info.value) is database.DatabaseException
    assert exc_info.value.args == (error,)
    assert exc_info.value.__cause__ is error
    fake_session.commit.assert_not_awaited()
    fake_session.rollback.assert_awaited_once_with()
    fake_session.close.assert_awaited_once_with()


async def test_session_rolls_back_when_commit_fails(mocker, real_database_api):
    error = RuntimeError("commit failed")
    ses = _FakeSession(mocker, commit_error=error)
    mocker.patch.object(database, "AsyncSession", return_value=ses)

    with pytest.raises(database.DatabaseException) as exc_info:
        async with real_database_api.session():
            pass

    assert exc_info.value.__cause__ is error
    ses.rollback.assert_awaited_once_with()
    ses.close.assert_awaited_once_with()


@pytest.mark.parametrize(
    "error",
    [
        ValueError("page must be positive"),
        database.NotFoundException("Note id=1 not found"),
        database.ConflictException("Material is not in the queue"),
    ],
    ids=["value-error", "not-found", "conflict"],
)
async def test_session_flattens_domain_errors_current_behaviour(
    fake_session,
    real_database_api,
    error,
):
    with pytest.raises(database.DatabaseException) as exc_info:
        async with real_database_api.session():
            raise error

    assert type(exc_info.value) is database.DatabaseException
    assert exc_info.value.__cause__ is error
    fake_session.rollback.assert_awaited_once_with()


async def test_session_closes_without_rollback_on_cancellation(
    fake_session,
    real_database_api,
):
    class _Cancelled(BaseException):
        pass

    with pytest.raises(_Cancelled):
        async with real_database_api.session():
            raise _Cancelled

    fake_session.commit.assert_not_awaited()
    fake_session.rollback.assert_not_awaited()
    fake_session.close.assert_awaited_once_with()


async def test_transaction_begins_inside_session_and_commits(
    monkeypatch,
    fake_session,
    real_database_api,
):
    monkeypatch.setattr(database, "session", real_database_api.session)

    async with real_database_api.transaction() as ses:
        assert ses is fake_session
        assert fake_session.begin_events == ["enter"]
        fake_session.commit.assert_not_awaited()

    assert fake_session.begin_events == ["enter", "exit"]
    fake_session.commit.assert_awaited_once_with()
    fake_session.close.assert_awaited_once_with()


async def test_transaction_passes_kwargs_to_session(
    mocker, monkeypatch, real_database_api
):
    ses = _FakeSession(mocker)
    session_class = mocker.patch.object(database, "AsyncSession", return_value=ses)
    monkeypatch.setattr(database, "session", real_database_api.session)

    async with real_database_api.transaction(autoflush=False):
        pass

    session_class.assert_called_once_with(autoflush=False, bind=database.engine)


async def test_transaction_rolls_back_and_wraps_error(
    monkeypatch,
    fake_session,
    real_database_api,
):
    monkeypatch.setattr(database, "session", real_database_api.session)
    error = RuntimeError("boom")

    with pytest.raises(database.DatabaseException) as exc_info:
        async with real_database_api.transaction():
            raise error

    assert exc_info.value.__cause__ is error
    assert fake_session.begin_events == ["enter", "exit"]
    fake_session.commit.assert_not_awaited()
    fake_session.rollback.assert_awaited_once_with()
    fake_session.close.assert_awaited_once_with()


def _patch_session(mocker, *, scalar):
    ses = SimpleNamespace(scalar=scalar)

    @asynccontextmanager
    async def _session(**_kwargs):
        yield ses

    mocker.patch.object(database, "session", _session)


@pytest.mark.parametrize("alive", [True, False], ids=["alive", "not-alive"])
async def test_readiness_returns_the_query_result(mocker, alive):
    scalar = mocker.AsyncMock(return_value=alive)
    _patch_session(mocker, scalar=scalar)

    assert await database.readiness() is alive

    (stmt,), _ = scalar.await_args
    assert str(stmt) == "SELECT 1 + 1 = 2"


async def test_readiness_is_false_when_query_fails(mocker):
    _patch_session(mocker, scalar=mocker.AsyncMock(side_effect=OSError("refused")))

    assert await database.readiness() is False


async def test_readiness_is_false_when_session_cannot_be_opened(mocker):
    @asynccontextmanager
    async def _session(**_kwargs):
        raise database.DatabaseException("no connection")
        yield

    mocker.patch.object(database, "session", _session)

    assert await database.readiness() is False


def test_drop_table_is_cascaded_on_postgresql():
    ddl = DropTable(models.Materials).compile(dialect=postgresql.dialect())

    assert str(ddl) == "\nDROP TABLE materials CASCADE"


def test_drop_table_is_not_cascaded_on_other_dialects():
    ddl = DropTable(models.Materials).compile(dialect=sqlite.dialect())

    assert str(ddl) == "\nDROP TABLE materials"


def test_drop_table_if_exists_is_cascaded_on_postgresql():
    ddl = DropTable(models.Notes, if_exists=True).compile(dialect=postgresql.dialect())

    assert str(ddl) == "\nDROP TABLE IF EXISTS notes CASCADE"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ({"a": 1}, '{"a":1}'),
        ([], "[]"),
        (["тег", "tag"], '["тег","tag"]'),
        (None, "null"),
        ("🙂", '"🙂"'),
    ],
    ids=["dict", "empty-list", "cyrillic", "none", "emoji"],
)
def test_json_serializer_returns_compact_utf8_string(value, expected):
    assert database._json_serializer(value) == expected


def test_json_serializer_rejects_unsupported_type():
    with pytest.raises(TypeError):
        database._json_serializer({1, 2})


def test_engine_uses_pinned_settings():
    assert database.engine.url.render_as_string(hide_password=False) == settings.DB_URI
    assert database.engine.url.port == 1
    assert database.engine.dialect.name == "postgresql"
    assert database.engine.dialect.driver == "asyncpg"


def _normalized(query: str) -> str:
    return " ".join(query.split())


def test_repeat_notes_matview_query_matches_the_migration():
    spec = importlib.util.spec_from_file_location(
        "alembic_shared_sql",
        REPOSITORY_ROOT / "migrations" / "alembic" / "sql.py",
    )
    migration_sql = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration_sql)

    assert _normalized(database.REPEAT_NOTES_MATVIEW_QUERY) == _normalized(
        migration_sql.REPEAT_NOTES_MATVIEW_V2,
    )


async def test_create_repeat_notes_matview_executes_the_query(mocker):
    conn = SimpleNamespace(execute=mocker.AsyncMock())

    await database.create_repeat_notes_matview(conn)

    (stmt,), _ = conn.execute.await_args
    assert conn.execute.await_count == 1
    assert stmt.text == database.REPEAT_NOTES_MATVIEW_QUERY
    assert "CREATE MATERIALIZED VIEW IF NOT EXISTS mvw_repeat_notes" in stmt.text
    assert stmt.text.rstrip().endswith("WITH NO DATA;")


async def test_recreate_db_drops_creates_and_builds_matview_in_one_transaction(mocker):
    conn = mocker.Mock()
    conn.run_sync = mocker.AsyncMock()
    conn.execute = mocker.AsyncMock()
    events: list[str] = []

    @asynccontextmanager
    async def _begin():
        events.append("begin")
        yield conn
        events.append("commit")

    mocker.patch.object(database, "engine", SimpleNamespace(begin=_begin))

    await database.recreate_db()

    assert events == ["begin", "commit"]
    assert conn.mock_calls[:2] == [
        mocker.call.run_sync(models.metadata.drop_all),
        mocker.call.run_sync(models.metadata.create_all),
    ]
    assert len(conn.mock_calls) == 3
    (stmt,), _ = conn.execute.await_args
    assert stmt.text == database.REPEAT_NOTES_MATVIEW_QUERY


class _FakeMigrationEngine:
    def __init__(self, mocker, *, tables: list[str], connect_error: Exception | None):
        self._mocker = mocker
        self._tables = tables
        self._connect_error = connect_error
        self.dispose = mocker.AsyncMock()
        self.inspected: list[object] = []

    @asynccontextmanager
    async def connect(self):
        if self._connect_error:
            raise self._connect_error

        sync_conn = object()

        async def _run_sync(fn):
            return fn(sync_conn)

        inspector = self._mocker.Mock()
        inspector.get_table_names.return_value = self._tables

        def _inspect(conn):
            self.inspected.append(conn)
            assert conn is sync_conn
            return inspector

        self._mocker.patch.object(database, "inspect", _inspect)
        yield SimpleNamespace(run_sync=_run_sync)


@pytest.fixture
def migration_engine(mocker):
    def _install(
        tables: list[str],
        connect_error: Exception | None = None,
    ) -> _FakeMigrationEngine:
        engine = _FakeMigrationEngine(mocker, tables=tables, connect_error=connect_error)
        engine.factory = mocker.patch.object(
            database,
            "create_async_engine",
            return_value=engine,
        )
        return engine

    return _install


@pytest.mark.parametrize(
    ("tables", "expected"),
    [
        ([], False),
        (["materials"], True),
        (["materials", "notes", "cards"], True),
        (["alembic_version"], False),
        (["alembic_version", "materials"], False),
        (["notes", "cards"], False),
        (["materials", "materials"], True),
        (["Materials"], False),
    ],
    ids=[
        "empty-database",
        "only-materials",
        "legacy-schema",
        "only-alembic-version",
        "versioned-schema",
        "tables-without-materials",
        "duplicated-names",
        "name-is-case-sensitive",
    ],
)
async def test_is_unversioned_db(migration_engine, tables, expected):
    engine = migration_engine(tables)

    assert await database._is_unversioned_db() is expected

    engine.factory.assert_called_once_with(settings.DB_URI)
    assert len(engine.inspected) == 1
    engine.dispose.assert_awaited_once_with()


async def test_is_unversioned_db_disposes_engine_when_connection_fails(migration_engine):
    engine = migration_engine([], connect_error=OSError("refused"))

    with pytest.raises(OSError, match="refused"):
        await database._is_unversioned_db()

    engine.dispose.assert_awaited_once_with()


@pytest.fixture
def alembic_command(mocker):
    from alembic import command

    manager = mocker.Mock()
    mocker.patch.object(command, "stamp", manager.stamp)
    mocker.patch.object(command, "upgrade", manager.upgrade)
    return manager


def _patch_unversioned(mocker, *, is_unversioned: bool):
    probe = mocker.patch.object(database, "_is_unversioned_db", mocker.Mock())
    # a sync test must not spin a second loop next to the session-scoped one
    run = mocker.patch.object(database.asyncio, "run", return_value=is_unversioned)
    return probe, run


def test_migrate_db_stamps_baseline_before_upgrading_unversioned_database(
    mocker,
    alembic_command,
):
    probe, run = _patch_unversioned(mocker, is_unversioned=True)

    database.migrate_db()

    run.assert_called_once_with(probe.return_value)
    assert [call[0] for call in alembic_command.mock_calls] == ["stamp", "upgrade"]
    stamp_config, stamp_revision = alembic_command.stamp.call_args.args
    upgrade_config, upgrade_revision = alembic_command.upgrade.call_args.args
    assert stamp_revision == "0001"
    assert upgrade_revision == "head"
    assert stamp_config is upgrade_config
    assert stamp_config.config_file_name == "alembic.ini"


def test_migrate_db_only_upgrades_versioned_database(mocker, alembic_command):
    _patch_unversioned(mocker, is_unversioned=False)

    database.migrate_db()

    alembic_command.stamp.assert_not_called()
    assert alembic_command.upgrade.call_count == 1
    config, revision = alembic_command.upgrade.call_args.args
    assert revision == "head"
    assert config.config_file_name == "alembic.ini"


def test_migrate_db_does_not_upgrade_when_stamp_fails(mocker, alembic_command):
    _patch_unversioned(mocker, is_unversioned=True)
    alembic_command.stamp.side_effect = RuntimeError("stamp failed")

    with pytest.raises(RuntimeError, match="stamp failed"):
        database.migrate_db()

    alembic_command.upgrade.assert_not_called()


async def test_create_db_runs_migration_off_the_event_loop(mocker):
    import threading

    threads: list[int] = []
    migrate = mocker.patch.object(
        database,
        "migrate_db",
        side_effect=lambda: threads.append(threading.get_ident()),
    )

    await database.create_db()

    migrate.assert_called_once_with()
    assert threads != [threading.get_ident()]


def test_min_max_defaults():
    result = database.MinMax(count=0, date=datetime.date(2024, 1, 2))

    assert result.model_dump() == {
        "log_id": "",
        "material_id": "",
        "material_title": "",
        "count": 0,
        "date": datetime.date(2024, 1, 2),
    }


def test_min_max_requires_count_and_date():
    with pytest.raises(ValidationError) as exc_info:
        database.MinMax()

    assert sorted(error["loc"] for error in exc_info.value.errors()) == [
        ("count",),
        ("date",),
    ]
