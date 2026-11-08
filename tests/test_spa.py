import logging

from starlette.routing import Mount

from tracker.common import settings, spa
from tracker.main import app


def test_spa_response_serves_index():
    response = spa.spa_response()

    assert response.path == spa.SPA_INDEX
    assert response.media_type == "text/html"


def test_check_spa_bundle_warns_when_index_is_missing(tmp_path, caplog):
    caplog.set_level(logging.WARNING, logger=settings.LOGGER_NAME)

    assert spa.check_spa_bundle(tmp_path / "index.html") is False

    warnings = [
        r
        for r in caplog.records
        if r.name == settings.LOGGER_NAME and r.levelno == logging.WARNING
    ]
    assert len(warnings) == 1


def test_check_spa_bundle_is_silent_when_index_exists(tmp_path, caplog):
    index = tmp_path / "index.html"
    index.write_text("<html></html>")

    assert spa.check_spa_bundle(index) is True
    assert not [r for r in caplog.records if r.name == settings.LOGGER_NAME]


def test_only_the_spa_bundle_is_mounted():
    mounts = {r.path for r in app.routes if isinstance(r, Mount)}

    assert "/static/app-spa" in mounts
    assert "/static" not in mounts
