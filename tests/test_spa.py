import logging
from collections.abc import AsyncGenerator

import httpx
import pytest
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


@pytest.fixture
async def client(tmp_path, monkeypatch) -> AsyncGenerator[httpx.AsyncClient]:
    index = tmp_path / "index.html"
    index.write_text("<html>spa</html>")
    monkeypatch.setattr(spa, "SPA_INDEX", index)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.parametrize(
    "path",
    ["/", "/notes", "/notes/123/update", "/materials/reading", "/new-section/page"],
)
async def test_client_routes_get_spa_index(client, path):
    response = await client.get(path)

    assert response.status_code == 200
    assert response.text == "<html>spa</html>"


@pytest.mark.parametrize(
    "path",
    ["/api/v1/unknown", "/api", "/static/style.css", "/static/app-spa/missing.js"],
)
async def test_api_and_static_paths_are_not_served_the_spa(client, path):
    response = await client.get(path)

    assert response.status_code == 404
    assert "spa" not in response.text


async def test_service_routes_are_not_shadowed(client):
    response = await client.get("/readiness")

    assert response.headers["content-type"].startswith("application/json")
