import logging
import uuid

import pytest

from kafka import debezium_parser
from tracker.common import kafka, settings


def _note_payload(*, note_id: uuid.UUID, is_deleted: bool = False) -> dict:
    return {
        "note_id": str(note_id),
        "material_id": str(uuid.uuid4()),
        "content": "content",
        "added_at": 1_700_000_000_000_000,
        "chapter": "1",
        "page": 1,
        "tags": "[]",
        "is_deleted": is_deleted,
        "note_number": 1,
    }


@pytest.fixture
def repeat_note(mocker):
    return mocker.patch.object(kafka, "repeat_note", mocker.AsyncMock())


async def test_to_notify_sends_note_id(repeat_note):
    note_id = uuid.uuid4()
    record = debezium_parser.Record(after=_note_payload(note_id=note_id))

    await debezium_parser._to_notify(record)

    repeat_note.assert_awaited_once_with(note_id)


async def test_to_notify_skips_deleted_note(repeat_note):
    note_id = uuid.uuid4()
    record = debezium_parser.Record(
        before=_note_payload(note_id=note_id),
        after=_note_payload(note_id=note_id, is_deleted=True),
    )

    await debezium_parser._to_notify(record)

    repeat_note.assert_not_awaited()


async def test_to_notify_drops_notification_when_kafka_fails(repeat_note, caplog):
    note_id = uuid.uuid4()
    repeat_note.side_effect = kafka.KafkaSendError("broker down")
    record = debezium_parser.Record(after=_note_payload(note_id=note_id))

    await debezium_parser._to_notify(record)

    errors = [
        r
        for r in caplog.records
        if r.name == settings.LOGGER_NAME and r.levelno >= logging.ERROR
    ]
    assert len(errors) == 1
    assert str(note_id) in errors[0].getMessage()
    assert errors[0].exc_info is None
