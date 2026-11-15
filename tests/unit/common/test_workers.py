import importlib.util
import logging
import signal
from pathlib import Path

import pytest

from tracker.common import settings, workers


GUNICORN_CONF = Path(__file__).resolve().parents[3] / "gunicorn.conf.py"


@pytest.fixture(autouse=True)
def no_reloader(mocker):
    mocker.patch.object(workers, "_reloader", None)


def test_reload_workers_calls_the_registered_reloader(mocker):
    reloader = mocker.Mock()
    workers.set_reloader(reloader)

    assert workers.reload_workers() is True
    reloader.assert_called_once_with()


def test_reload_workers_without_a_reloader_asks_for_a_manual_restart(caplog):
    caplog.set_level(logging.WARNING, logger=settings.LOGGER_NAME)

    assert workers.reload_workers() is False
    assert [record.getMessage() for record in caplog.records] == [
        "No workers reloader is registered, restart tracker-app manually",
    ]


def test_gunicorn_post_fork_registers_a_hangup_of_the_master(mocker):
    spec = importlib.util.spec_from_file_location("gunicorn_conf", GUNICORN_CONF)
    conf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(conf)
    kill = mocker.patch.object(conf.os, "kill")

    conf.post_fork(mocker.Mock(pid=4242), mocker.Mock())
    workers.reload_workers()

    kill.assert_called_once_with(4242, signal.SIGHUP)
