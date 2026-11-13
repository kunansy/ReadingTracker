import runpy
from pathlib import Path

import pytest

from tracker.common import database


GUNICORN_CONF = Path(__file__).resolve().parents[3] / "gunicorn.conf.py"


@pytest.fixture
def config() -> dict:
    return runpy.run_path(str(GUNICORN_CONF))


def test_on_starting_migrates_the_database_once(config, mocker):
    migrate = mocker.patch.object(database, "migrate_db")
    server = mocker.Mock()

    result = config["on_starting"](server)

    assert result is None
    migrate.assert_called_once_with()
    assert server.mock_calls == []


def test_on_starting_propagates_migration_failure(config, mocker):
    mocker.patch.object(database, "migrate_db", side_effect=RuntimeError("no database"))

    with pytest.raises(RuntimeError, match="no database"):
        config["on_starting"](mocker.Mock())


def test_config_defines_only_the_server_hook(config):
    hooks = sorted(
        name
        for name, value in config.items()
        if callable(value) and name.startswith("on_")
    )

    assert hooks == ["on_starting"]
