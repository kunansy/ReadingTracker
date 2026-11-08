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


async def test_to_notify_propagates_kafka_failure(repeat_note):
    repeat_note.side_effect = kafka.KafkaSendError("broker down")
    record = debezium_parser.Record(after=_note_payload(note_id=uuid.uuid4()))

    with pytest.raises(kafka.KafkaSendError):
        await debezium_parser._to_notify(record)


@pytest.fixture
def two_records(mocker) -> dict:
    records = [
        debezium_parser.Record(after=_note_payload(note_id=uuid.uuid4())) for _ in range(2)
    ]
    state = {"records": records, "closed": False}

    async def _iter_updates():
        try:
            for record in records:
                yield record
        finally:
            state["closed"] = True

    mocker.patch.object(debezium_parser, "iter_updates", _iter_updates)
    mocker.patch.object(settings, "EX_ENABLE_KAFKA_TO_NOTIFY", True)
    return state


async def test_parse_processes_every_record(two_records, repeat_note, mocker):
    to_search_engine = mocker.patch.object(
        debezium_parser, "_to_search_engine", mocker.AsyncMock()
    )

    await debezium_parser.parse()

    records = two_records["records"]
    assert to_search_engine.await_args_list == [mocker.call(r) for r in records]
    assert repeat_note.await_args_list == [mocker.call(r.note_id) for r in records]


async def test_parse_stops_on_notify_failure_and_closes_the_stream(
    two_records, repeat_note, mocker
):
    to_search_engine = mocker.patch.object(
        debezium_parser, "_to_search_engine", mocker.AsyncMock()
    )
    repeat_note.side_effect = kafka.KafkaSendError("broker down")

    with pytest.raises(kafka.KafkaSendError):
        await debezium_parser.parse()

    to_search_engine.assert_awaited_once_with(two_records["records"][0])
    assert two_records["closed"]
