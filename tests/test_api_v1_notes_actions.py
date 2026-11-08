import uuid
from collections.abc import AsyncGenerator

import httpx
import pytest

from tracker.api.v1 import notes as notes_api
from tracker.common import database
from tracker.main import app
from tracker.notes import db as notes_db


@pytest.fixture
async def client() -> AsyncGenerator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def _not_found(mocker):
    return mocker.AsyncMock(side_effect=database.NotFoundException("Note not found"))


async def test_delete_note(client, mocker):
    note_id = uuid.uuid4()
    delete_note = mocker.patch.object(notes_db, "delete_note", mocker.AsyncMock())

    response = await client.delete(f"/api/v1/notes/{note_id}")

    assert response.status_code == 204
    delete_note.assert_awaited_once_with(note_id=note_id)


async def test_delete_missing_note_is_404(client, mocker):
    mocker.patch.object(notes_db, "delete_note", _not_found(mocker))

    response = await client.delete(f"/api/v1/notes/{uuid.uuid4()}")

    assert response.status_code == 404


async def test_restore_note(client, mocker):
    note_id = uuid.uuid4()
    restore_note = mocker.patch.object(notes_db, "restore_note", mocker.AsyncMock())

    response = await client.post(f"/api/v1/notes/{note_id}/restore")

    assert response.status_code == 204
    restore_note.assert_awaited_once_with(note_id=note_id)


async def test_restore_missing_note_is_404(client, mocker):
    mocker.patch.object(notes_db, "restore_note", _not_found(mocker))

    response = await client.post(f"/api/v1/notes/{uuid.uuid4()}/restore")

    assert response.status_code == 404


async def test_insert_note_to_repeat_queue(client, mocker):
    note_id = uuid.uuid4()
    mocker.patch.object(notes_db, "get_note_api", mocker.AsyncMock())
    repeat_note = mocker.patch.object(notes_api.kafka, "repeat_note", mocker.AsyncMock())

    response = await client.post(f"/api/v1/notes/{note_id}/repeat-queue")

    assert response.status_code == 204
    repeat_note.assert_awaited_once_with(note_id)


async def test_insert_missing_note_to_repeat_queue_is_404(client, mocker):
    mocker.patch.object(notes_db, "get_note_api", _not_found(mocker))
    repeat_note = mocker.patch.object(notes_api.kafka, "repeat_note", mocker.AsyncMock())

    response = await client.post(f"/api/v1/notes/{uuid.uuid4()}/repeat-queue")

    assert response.status_code == 404
    repeat_note.assert_not_awaited()


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

    assert response.status_code in {404, 405}
