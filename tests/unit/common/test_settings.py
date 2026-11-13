import datetime
import importlib
import logging
import os
from pathlib import Path

import environs
import pytest

from tests.conftest import TEST_ENVIRONMENT
from tracker.common import settings


@pytest.fixture
def load_settings(monkeypatch, tmp_path):
    """Re-execute the settings module in a controlled environment and cwd.

    The module state and `os.environ` are put back afterwards, so objects that other
    modules hold (`settings.env`, `settings.DATA_DIR`, ...) stay the very same ones.
    """
    saved_module = dict(vars(settings))
    saved_environ = dict(os.environ)
    monkeypatch.chdir(tmp_path)
    # the developer's .env must never fill the gaps a test leaves on purpose
    monkeypatch.setattr(environs.Env, "read_env", lambda *_args, **_kwargs: False)

    def _load(*, without: tuple[str, ...] = (), **overrides: str):
        environment = {**TEST_ENVIRONMENT, **overrides}
        for name in without:
            del environment[name]

        os.environ.clear()
        os.environ.update(environment)
        return importlib.reload(settings)

    yield _load

    vars(settings).clear()
    vars(settings).update(saved_module)
    os.environ.clear()
    os.environ.update(saved_environ)


def test_reload_with_test_environment_gives_pinned_values(load_settings):
    loaded = load_settings()

    assert loaded.TRACKER_URL == "http://tracker.test"
    assert loaded.API_DEBUG is False
    assert loaded.DB_HOST == "127.0.0.1"
    assert loaded.DB_PORT == 1
    assert loaded.DB_NAME == "tracker_unit"
    assert loaded.DB_USERNAME == "tracker"
    assert loaded.DB_PASSWORD == "tracker"
    assert loaded.DB_TIMEOUT == 5
    assert loaded.DB_ISOLATION_LEVEL == "REPEATABLE READ"
    assert (
        loaded.DB_URI == "postgresql+asyncpg://tracker:tracker@127.0.0.1:1/tracker_unit"
    )
    assert loaded.LOGGER_NAME == "ReadingTrackerTests"
    assert loaded.LOGGER_LEVEL == logging.DEBUG
    assert loaded.DRIVE_CREDS == {}
    assert loaded.MANTICORE_MYSQL_HOST == "127.0.0.1"
    assert loaded.MANTICORE_MYSQL_PORT == 1
    assert loaded.MANTICORE_MYSQL_DB_NAME == "Manticore"
    assert loaded.BACKUP_TARGET == "127.0.0.1:1"
    assert loaded.YOUTUBE_API_URL == "https://youtube.test/v3/videos"
    assert loaded.YOUTUBE_API_KEY == "test-youtube-key"
    assert loaded.KAFKA_URL == "127.0.0.1:1"
    assert loaded.KAFKA_REPEAT_NOTES_TOPIC == "repeat-notes-test"
    assert loaded.KAFKA_CACHE_NOTES_TOPIC == "cache-notes-test"
    assert loaded.KAFKA_CONNECT_TIMEOUT == 1
    assert loaded.EX_ENABLE_KAFKA_TO_NOTIFY is False
    assert loaded.EX_DARKMODE_ENABLE == datetime.time(15)


def test_optional_variables_fall_back_to_defaults(load_settings):
    loaded = load_settings(
        without=(
            "TRACKER_URL",
            "API_DEBUG",
            "DB_TIMEOUT",
            "DB_ISOLATION_LEVEL",
            "LOGGER_NAME",
            "LOGGER_LEVEL",
            "MANTICORE_MYSQL_PORT",
            "MANTICORE_MYSQL_DB_NAME",
            "YOUTUBE_API_URL",
            "KAFKA_HOST",
            "KAFKA_PORT",
            "KAFKA_CONNECT_TIMEOUT",
            "EX_ENABLE_KAFKA_TO_NOTIFY",
            "EX_DARKMODE_ENABLE",
        ),
    )

    assert loaded.TRACKER_URL == "http://tracker-app:8000"
    assert loaded.API_DEBUG is False
    assert loaded.DB_TIMEOUT == 5
    assert loaded.DB_ISOLATION_LEVEL == "REPEATABLE READ"
    assert loaded.LOGGER_NAME == "ReadingTracker"
    assert loaded.LOGGER_LEVEL == logging.DEBUG
    assert loaded.MANTICORE_MYSQL_PORT == 9306
    assert loaded.MANTICORE_MYSQL_DB_NAME == "Manticore"
    assert loaded.YOUTUBE_API_URL == "https://youtube.googleapis.com/youtube/v3/videos"
    assert loaded.KAFKA_URL == "localhost:9092"
    assert loaded.KAFKA_CONNECT_TIMEOUT == 3
    assert loaded.EX_ENABLE_KAFKA_TO_NOTIFY is False
    assert loaded.EX_DARKMODE_ENABLE == datetime.time(15)


def test_values_are_parsed_from_environment(load_settings):
    loaded = load_settings(
        API_DEBUG="true",
        DB_PORT="5432",
        DB_PASSWORD="p@ss:word/1",
        DB_ISOLATION_LEVEL="SERIALIZABLE",
        LOGGER_LEVEL="WARNING",
        DRIVE_CREDS='{"type": "service_account", "nested": {"a": [1, 2]}}',
        EX_ENABLE_KAFKA_TO_NOTIFY="1",
        EX_DARKMODE_ENABLE="07:30:15",
    )

    assert loaded.API_DEBUG is True
    assert loaded.DB_PORT == 5432
    assert loaded.DB_ISOLATION_LEVEL == "SERIALIZABLE"
    assert loaded.LOGGER_LEVEL == logging.WARNING
    assert loaded.DRIVE_CREDS == {"type": "service_account", "nested": {"a": [1, 2]}}
    assert loaded.EX_ENABLE_KAFKA_TO_NOTIFY is True
    assert loaded.EX_DARKMODE_ENABLE == datetime.time(7, 30, 15)


def test_db_uri_does_not_escape_the_password_current_behaviour(load_settings):
    loaded = load_settings(DB_PASSWORD="p@ss:word/1")

    assert loaded.DB_URI == (
        "postgresql+asyncpg://tracker:p@ss:word/1@127.0.0.1:1/tracker_unit"
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "BUG: tracker/common/settings.py:29 the validator returns False instead of "
        "raising, which marshmallow 4 ignores, so a trailing slash is accepted"
    ),
)
@pytest.mark.parametrize(
    "url",
    ["http://tracker.test/", "/", "http://tracker.test//"],
    ids=["trailing-slash", "only-slash", "double-slash"],
)
def test_tracker_url_with_trailing_slash_is_rejected(load_settings, url):
    with pytest.raises(environs.EnvValidationError, match="TRACKER_URL"):
        load_settings(TRACKER_URL=url)


def test_tracker_url_with_path_is_accepted(load_settings):
    assert load_settings(TRACKER_URL="https://host/prefix").TRACKER_URL == (
        "https://host/prefix"
    )


@pytest.mark.parametrize(
    "level",
    ["READ UNCOMMITTED", "READ COMMITTED", "REPEATABLE READ", "SERIALIZABLE"],
)
def test_supported_isolation_levels_are_accepted(load_settings, level):
    assert load_settings(DB_ISOLATION_LEVEL=level).DB_ISOLATION_LEVEL == level


@pytest.mark.parametrize(
    "level",
    ["AUTOCOMMIT", "serializable", "", "REPEATABLE  READ"],
    ids=["autocommit", "lower-case", "empty", "double-space"],
)
def test_unsupported_isolation_level_is_rejected(load_settings, level):
    with pytest.raises(environs.EnvValidationError, match="invalid isolation level"):
        load_settings(DB_ISOLATION_LEVEL=level)


@pytest.mark.parametrize(
    "name",
    [
        "DB_HOST",
        "DB_PORT",
        "DB_NAME",
        "DB_USERNAME",
        "DB_PASSWORD",
        "DRIVE_CREDS",
        "MANTICORE_MYSQL_HOST",
        "BACKUP_HOST",
        "BACKUP_PORT",
        "YOUTUBE_API_KEY",
        "KAFKA_REPEAT_NOTES_TOPIC",
        "KAFKA_CACHE_NOTES_TOPIC",
    ],
)
def test_missing_required_variable_is_an_error(load_settings, name):
    with pytest.raises(environs.EnvError, match=f'"{name}" not set'):
        load_settings(without=(name,))


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("DB_PORT", "five"),
        ("DB_TIMEOUT", "1.5"),
        ("API_DEBUG", "maybe"),
        ("LOGGER_LEVEL", "LOUD"),
        ("EX_DARKMODE_ENABLE", "25:00:00"),
        ("KAFKA_PORT", ""),
    ],
    ids=["port", "timeout", "bool", "log-level", "time", "empty-port"],
)
def test_unparsable_value_is_an_error(load_settings, name, value):
    with pytest.raises(environs.EnvError, match=name):
        load_settings(**{name: value})


@pytest.mark.parametrize(
    "creds",
    ["{", "not json", "", "{'single': 'quotes'}"],
    ids=["truncated", "text", "empty", "python-dict"],
)
def test_invalid_drive_creds_json_is_an_error(load_settings, creds):
    with pytest.raises(ValueError):
        load_settings(DRIVE_CREDS=creds)


def test_api_version_is_read_from_version_file(load_settings, tmp_path):
    (tmp_path / "VERSION").write_text("  286\n")

    assert load_settings().API_VERSION == "286"


def test_api_version_defaults_without_version_file(load_settings):
    assert load_settings().API_VERSION == "0.1.0"


def test_data_dir_is_created_in_working_directory(load_settings, tmp_path):
    loaded = load_settings()

    assert loaded.DATA_DIR == Path("data/")
    assert (tmp_path / "data").is_dir()


def test_existing_data_dir_is_kept(load_settings, tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "file.txt").write_text("kept")

    load_settings()

    assert (tmp_path / "data" / "file.txt").read_text() == "kept"


def test_environment_is_cleared_except_path_and_metrics_dir(load_settings):
    load_settings(
        PATH="/usr/bin:/bin",
        PROMETHEUS_MULTIPROC_DIR="/tmp/metrics",
        SOME_SECRET="secret",
    )

    assert dict(os.environ) == {
        "PATH": "/usr/bin:/bin",
        "PROMETHEUS_MULTIPROC_DIR": "/tmp/metrics",
    }


def test_environment_is_emptied_without_path_and_metrics_dir(load_settings):
    load_settings()

    assert dict(os.environ) == {}


@pytest.mark.parametrize(
    ("name", "kept"),
    [("PATH", {"PATH": "/bin"}), ("PROMETHEUS_MULTIPROC_DIR", {})],
    ids=["only-path", "empty-metrics-dir"],
)
def test_empty_path_or_metrics_dir_is_not_restored(load_settings, name, kept):
    load_settings(**({"PATH": "/bin"} if name == "PATH" else {name: ""}))

    assert dict(os.environ) == kept


def test_environment_is_not_cleared_when_loading_fails(load_settings):
    with pytest.raises(environs.EnvError):
        load_settings(without=("DB_HOST",), SOME_SECRET="secret")

    assert os.environ["SOME_SECRET"] == "secret"


def test_constants():
    assert settings.DATE_FORMAT == "%Y-%m-%d"
    assert settings.DATETIME_FORMAT == "%Y-%m-%d %H:%M:%S"
    assert settings.DSN_TEMPLATE == (
        "postgresql+asyncpg://{username}:{password}@{host}:{port}/{db_name}"
    )


def test_settings_are_restored_after_a_reload(load_settings):
    env_before, data_dir_before = settings.env, settings.DATA_DIR

    load_settings(TRACKER_URL="http://other.test", DB_PORT="5432")
    assert settings.TRACKER_URL == "http://other.test"

    # restore by hand what the fixture does on teardown, to assert it in a test
    load_settings()
    assert settings.TRACKER_URL == "http://tracker.test"
    assert settings.DB_PORT == 1
    assert settings.env is not env_before
    assert settings.DATA_DIR == data_dir_before
