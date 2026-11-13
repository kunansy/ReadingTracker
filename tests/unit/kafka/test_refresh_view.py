import asyncio
import importlib
import inspect
import sys
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest


MODULE_NAME = "kafka.refresh_view"


@pytest.fixture
def imported(mocker, monkeypatch):
    """The module runs `asyncio.run(refresh_view())` at import: capture that call."""
    started = []

    def _run(coroutine):
        started.append(coroutine.cr_code.co_name)
        coroutine.close()

    monkeypatch.delitem(sys.modules, MODULE_NAME, raising=False)
    mocker.patch.object(asyncio, "run", _run)

    module = importlib.import_module(MODULE_NAME)
    yield SimpleNamespace(module=module, started=started)

    sys.modules.pop(MODULE_NAME, None)


@pytest.fixture
def session(mocker):
    events: list[str] = []
    executed: list = []

    async def _execute(stmt):
        executed.append(stmt)
        events.append("execute")

    @asynccontextmanager
    async def _session(**_kwargs):
        events.append("open")
        yield SimpleNamespace(execute=_execute)
        events.append("commit")

    mocker.patch("tracker.common.database.session", _session)
    return SimpleNamespace(events=events, executed=executed)


def test_import_runs_refresh_view_once(imported):
    assert imported.started == ["refresh_view"]
    assert inspect.iscoroutinefunction(imported.module.refresh_view)


def test_refresh_statement(imported):
    assert imported.module.REFRESH_REPEAT_NOTES_STMT.text == (
        "REFRESH MATERIALIZED VIEW mvw_repeat_notes;"
    )


async def test_refresh_view_executes_refresh_in_a_session(imported, session):
    await imported.module.refresh_view()

    assert session.events == ["open", "execute", "commit"]
    assert session.executed == [imported.module.REFRESH_REPEAT_NOTES_STMT]


async def test_refresh_view_propagates_database_error(imported, mocker):
    from tracker.common import database

    @asynccontextmanager
    async def _session(**_kwargs):
        raise database.DatabaseException("view is not populated")
        yield

    mocker.patch("tracker.common.database.session", _session)

    with pytest.raises(database.DatabaseException, match="view is not populated"):
        await imported.module.refresh_view()
