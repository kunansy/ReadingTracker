import logging

import httpx
import pytest
from fastapi import HTTPException
from starlette.applications import Starlette
from starlette.routing import Mount

from tracker.common import spa
from tracker.main import app


SPA_HTML = "<html>spa</html>"


@pytest.fixture
def spa_index(tmp_path, monkeypatch):
    index = tmp_path / "index.html"
    index.write_text(SPA_HTML)
    monkeypatch.setattr(spa, "SPA_INDEX", index)
    return index


def test_spa_response_serves_the_index_as_html():
    response = spa.spa_response()

    assert response.path == spa.SPA_INDEX
    assert response.media_type == "text/html"


def test_check_spa_bundle_warns_when_index_is_missing(tmp_path, tracker_log):
    index = tmp_path / "index.html"

    assert spa.check_spa_bundle(index) is False

    warnings = tracker_log(logging.WARNING)
    assert len(warnings) == 1
    assert warnings[0].getMessage() == (
        f"SPA bundle not found at {index}, run `npm run build`"
    )


def test_check_spa_bundle_is_silent_when_index_exists(spa_index, tracker_log):
    assert spa.check_spa_bundle(spa_index) is True
    assert tracker_log() == []


def test_only_the_spa_bundle_is_mounted():
    mounts = {r.path for r in app.routes if isinstance(r, Mount)}

    assert "/static/app-spa" in mounts
    assert "/static" not in mounts


def test_catch_all_is_the_last_route():
    assert app.routes[-1].path == "/{path:path}"


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/notes",
        "/notes/123/update",
        "/materials/reading",
        "/new-section/page",
        "/apis",
        "/statics/x",
        "/notes/api",
        "/API/v1",
        "/заметки",
    ],
)
async def test_client_route_gets_the_spa_index(client, spa_index, path):
    response = await client.get(path)

    assert response.status_code == 200
    assert response.text == SPA_HTML
    assert response.headers["content-type"].startswith("text/html")


@pytest.mark.parametrize(
    "path",
    ["/api/v1/unknown", "/api", "/api/", "/static", "/static/style.css"],
)
async def test_api_and_static_paths_are_not_served_the_spa(client, spa_index, path):
    response = await client.get(path)

    assert response.status_code == 404
    assert response.json() == {"detail": "Not found"}


async def test_missing_bundle_file_is_404_from_the_static_mount(client, spa_index):
    response = await client.get("/static/app-spa/missing.js")

    assert response.status_code == 404
    assert SPA_HTML not in response.text


async def _get_from_bundle(directory, path):
    bundle = Starlette(
        routes=[Mount("/", spa.SpaStaticFiles(directory=directory, check_dir=False))]
    )
    transport = httpx.ASGITransport(app=bundle)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        return await http.get(path)


async def test_bundle_mount_answers_404_when_the_directory_is_absent(tmp_path):
    response = await _get_from_bundle(tmp_path / "absent", "/app.js")

    assert response.status_code == 404


async def test_bundle_mount_serves_a_built_file(tmp_path):
    (tmp_path / "app.js").write_text("built")

    response = await _get_from_bundle(tmp_path, "/app.js")

    assert response.status_code == 200
    assert response.text == "built"


@pytest.mark.parametrize("path", ["api", "api/v1/x", "static", "static/app.js"])
async def test_catch_all_rejects_reserved_first_segment(path):
    with pytest.raises(HTTPException) as e:
        await spa.spa_catch_all(path)

    assert e.value.status_code == 404
    assert e.value.detail == "Not found"


@pytest.mark.parametrize("path", ["", "notes", "apiary/x", "x/api", "x/static"])
async def test_catch_all_serves_the_index_for_any_other_path(spa_index, path):
    response = await spa.spa_catch_all(path)

    assert response.path == spa_index


async def test_service_routes_are_not_shadowed(client, spa_index):
    response = await client.get("/liveness")

    assert response.json() == {"status": "ok"}


async def test_non_get_to_a_client_route_is_405(client, spa_index):
    response = await client.post("/notes")

    assert response.status_code == 405


async def test_missing_bundle_makes_spa_routes_503(client, tmp_path, monkeypatch):
    monkeypatch.setattr(spa, "SPA_INDEX", tmp_path / "absent.html")

    response = await client.get("/notes")

    assert response.status_code == 503
    assert response.json() == {"detail": "SPA bundle is not built"}


async def test_missing_bundle_keeps_reserved_prefixes_404(client, tmp_path, monkeypatch):
    monkeypatch.setattr(spa, "SPA_INDEX", tmp_path / "absent.html")

    response = await client.get("/api/unknown")

    assert response.status_code == 404


@pytest.mark.parametrize(
    ("method", "path", "status_code"),
    [("GET", "/api/v1/cards", 404), ("POST", "/api/v1/materials", 405)],
    ids=["get-is-swallowed-by-catch-all", "post-finds-only-the-catch-all"],
)
async def test_api_path_without_trailing_slash_is_not_redirected_current_behaviour(
    client, spa_index, method, path, status_code
):
    response = await client.request(method, path)

    assert response.status_code == status_code
    assert "location" not in response.headers


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("DELETE", "/notes/delete"),
        ("POST", "/notes/restore"),
        ("POST", "/notes/repeat-queue/insert"),
        ("POST", "/notes/update"),
    ],
)
async def test_legacy_note_writes_are_gone(client, method, path):
    response = await client.request(method, path)

    assert response.status_code == 405
