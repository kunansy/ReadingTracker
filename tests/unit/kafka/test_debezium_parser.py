import copy
import datetime
import logging
from uuid import UUID

import orjson
import pytest
from aiokafka import errors
from pydantic import ValidationError

from kafka import debezium_parser
from kafka.debezium_parser import Record
from tracker.common import kafka, manticoresearch, settings
from tracker.models import models


NOTE_ID = UUID("018e9dbe-1d3d-7a5a-b437-9bfa65171b42")
OTHER_NOTE_ID = UUID("1c2fc59d-5313-4615-9290-e8668abe2fc0")
MATERIAL_ID = UUID("688d59d1-6932-4795-a353-08463ea10c9c")
# Debezium sends `timestamp` columns as microseconds since the epoch
ADDED_AT_MICROSECONDS = 1_700_000_000_123_456
ADDED_AT = datetime.datetime(2023, 11, 14, 22, 13, 20, 123_000, tzinfo=datetime.UTC)


def _note_payload(
    *,
    note_id: UUID = NOTE_ID,
    is_deleted: bool = False,
    content: str = "content",
) -> dict:
    return {
        "note_id": str(note_id),
        "material_id": str(MATERIAL_ID),
        "content": content,
        "added_at": ADDED_AT_MICROSECONDS,
        "chapter": "1",
        "page": 1,
        "tags": '["tag"]',
        "is_deleted": is_deleted,
        "note_number": 1,
    }


def _message(*, before: dict | None, after: dict | None, offset: int = 0):
    class _Message:
        topic = "cache-notes-test"
        value = orjson.dumps({"payload": {"before": before, "after": after}})

    message = _Message()
    message.offset = offset
    return message


class _FakeConsumer:
    def __init__(self, mocker, messages: list, *, fail_with: Exception | None) -> None:
        self._messages = messages
        self._fail_with = fail_with
        self.events: list[str] = []
        self.start = mocker.AsyncMock(side_effect=lambda: self.events.append("start"))
        self.commit = mocker.AsyncMock(side_effect=lambda: self.events.append("commit"))
        self.stop = mocker.AsyncMock(side_effect=lambda: self.events.append("stop"))

    async def __aiter__(self):
        for message in self._messages:
            self.events.append(f"message {message.offset}")
            yield message
        if self._fail_with:
            raise self._fail_with


@pytest.fixture
def consumer(mocker):
    def _install(messages: list, fail_with: Exception | None = None) -> _FakeConsumer:
        consumer = _FakeConsumer(mocker, messages, fail_with=fail_with)
        consumer.factory = mocker.patch.object(
            debezium_parser,
            "AIOKafkaConsumer",
            return_value=consumer,
        )
        return consumer

    return _install


@pytest.fixture
def repeat_note(mocker):
    return mocker.patch.object(kafka, "repeat_note", mocker.AsyncMock())


@pytest.fixture
def search_engine(mocker):
    manager = mocker.Mock()
    manager.delete = mocker.patch.object(manticoresearch, "delete", mocker.AsyncMock())
    manager.update_content = mocker.patch.object(
        manticoresearch,
        "update_content",
        mocker.AsyncMock(),
    )
    return manager


def _error_messages(caplog) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if record.name == settings.LOGGER_NAME and record.levelno >= logging.ERROR
    ]


def test_record_parses_after_note():
    record = Record(after=_note_payload(content=" Текст заметки "))

    assert record.before is None
    assert record.after.note_id == NOTE_ID
    assert record.after.material_id == MATERIAL_ID
    assert record.after.content == "Текст заметки"
    assert record.after.tags == {"tag"}
    assert record.after.added_at == ADDED_AT


def test_record_converts_microseconds_and_drops_the_sub_millisecond_part():
    record = Record(after=_note_payload(), before=_note_payload())

    assert record.after.added_at == ADDED_AT
    assert record.before.added_at == ADDED_AT


@pytest.mark.parametrize("empty", [None, {}], ids=["none", "empty-dict"])
def test_record_treats_empty_after_and_before_as_absent(empty):
    record = Record(after=empty, before=empty)

    assert record.after is None
    assert record.before is None


def test_record_before_defaults_to_none():
    assert Record(after=None).before is None


def test_record_requires_after():
    with pytest.raises(ValidationError) as exc_info:
        Record()

    assert [(e["type"], e["loc"]) for e in exc_info.value.errors()] == [
        ("missing", ("after",)),
    ]


def test_record_rejects_extra_fields():
    with pytest.raises(ValidationError) as exc_info:
        Record(after=None, source={"table": "notes"})

    assert [(e["type"], e["loc"]) for e in exc_info.value.errors()] == [
        ("extra_forbidden", ("source",)),
    ]


@pytest.mark.parametrize("field", ["after", "before"])
def test_record_without_added_at_is_an_error(field):
    payload = _note_payload()
    del payload["added_at"]

    with pytest.raises(KeyError):
        Record(**{"after": None, field: payload})


@pytest.mark.xfail(
    strict=True,
    reason=(
        "BUG: kafka/debezium_parser.py:18 Record validates rows with notes.db.Note, "
        "which forbids extras and has no sort_key, so every row of the current notes "
        "table is rejected"
    ),
)
def test_record_accepts_every_column_of_the_notes_table():
    row = {
        **_note_payload(),
        "link_id": None,
        "title": None,
        "sort_key": f"{MATERIAL_ID}$$0000000001$$0000000001$${NOTE_ID}",
    }
    assert sorted(row) == sorted(models.Notes.c.keys())

    record = Record(after=row)

    assert record.note_id == NOTE_ID


@pytest.mark.xfail(
    strict=True,
    reason=(
        "BUG: kafka/debezium_parser.py:46 the before-validators divide added_at in the "
        "caller's dict in place"
    ),
)
@pytest.mark.parametrize("field", ["after", "before"])
def test_record_does_not_change_the_given_payload(field):
    payload = _note_payload()
    original = copy.deepcopy(payload)

    Record(**{"after": None, field: payload})

    assert payload == original


def test_same_payload_parsed_twice_gets_another_time_current_behaviour():
    payload = _note_payload()

    first = Record(after=payload)
    second = Record(after=payload)

    assert first.added_at == ADDED_AT
    # the second division turns milliseconds into seconds
    assert second.added_at == ADDED_AT.replace(microsecond=0)
    assert payload["added_at"] == ADDED_AT_MICROSECONDS // 1_000_000


def test_note_id_prefers_after():
    record = Record(
        after=_note_payload(note_id=NOTE_ID),
        before=_note_payload(note_id=OTHER_NOTE_ID),
    )

    assert record.note_id == NOTE_ID


def test_note_id_falls_back_to_before():
    record = Record(after=None, before=_note_payload(note_id=OTHER_NOTE_ID))

    assert record.note_id == OTHER_NOTE_ID


def test_note_id_without_after_and_before_is_an_error():
    with pytest.raises(ValueError, match="^Note id not found$"):
        Record(after=None).note_id


def test_content_is_taken_from_after():
    record = Record(
        after=_note_payload(content="new **content**"),
        before=_note_payload(content="old"),
    )

    assert record.content == "new **content**"


def test_content_without_after_is_an_error():
    with pytest.raises(ValueError, match="^Content not found$"):
        Record(after=None, before=_note_payload()).content


def test_added_at_is_taken_from_after():
    assert Record(after=_note_payload()).added_at == ADDED_AT


def test_added_at_without_after_is_an_error():
    with pytest.raises(ValueError, match="^Added at not found$"):
        Record(after=None, before=_note_payload()).added_at


RECORD_KINDS = {
    "insert": (
        lambda: Record(after=_note_payload()),
        {"insert": True, "update": False, "delete": False},
    ),
    "update": (
        lambda: Record(after=_note_payload(), before=_note_payload()),
        {"insert": False, "update": True, "delete": False},
    ),
    "soft-delete": (
        lambda: Record(after=_note_payload(is_deleted=True), before=_note_payload()),
        {"insert": False, "update": True, "delete": True},
    ),
    "restore": (
        lambda: Record(after=_note_payload(), before=_note_payload(is_deleted=True)),
        {"insert": False, "update": True, "delete": False},
    ),
    "insert-of-deleted": (
        lambda: Record(after=_note_payload(is_deleted=True)),
        {"insert": True, "update": False, "delete": True},
    ),
    "hard-delete": (
        lambda: Record(after=None, before=_note_payload()),
        {"insert": False, "update": False, "delete": True},
    ),
    "empty": (
        lambda: Record(after=None),
        {"insert": False, "update": False, "delete": True},
    ),
}


@pytest.mark.parametrize("case", RECORD_KINDS.values(), ids=RECORD_KINDS.keys())
def test_record_kind(case):
    make_record, expected = case
    record = make_record()

    assert {
        "insert": record.is_insert(),
        "update": record.is_update(),
        "delete": record.is_delete(),
    } == expected


async def test_iter_updates_yields_records_and_commits_after_each(consumer):
    fake = consumer(
        [
            _message(before=None, after=_note_payload(note_id=NOTE_ID), offset=1),
            _message(before=_note_payload(note_id=OTHER_NOTE_ID), after=None, offset=2),
        ],
    )

    records = []
    async for record in debezium_parser.iter_updates():
        fake.events.append(f"processed {record.note_id}")
        records.append(record)

    assert [(r.note_id, r.is_delete()) for r in records] == [
        (NOTE_ID, False),
        (OTHER_NOTE_ID, True),
    ]
    assert fake.events == [
        "start",
        "message 1",
        f"processed {NOTE_ID}",
        "commit",
        "message 2",
        f"processed {OTHER_NOTE_ID}",
        "commit",
        "stop",
    ]


async def test_iter_updates_subscribes_without_auto_commit(consumer):
    fake = consumer([])

    assert [record async for record in debezium_parser.iter_updates()] == []

    fake.factory.assert_called_once_with(
        "cache-notes-test",
        bootstrap_servers="127.0.0.1:1",
        group_id="parse_debezium",
        request_timeout_ms=1000,
        auto_offset_reset="earliest",
        enable_auto_commit=False,
    )
    assert fake.events == ["start", "stop"]


async def test_iter_updates_does_not_commit_message_whose_processing_failed(consumer):
    fake = consumer([_message(before=None, after=_note_payload(), offset=1)])
    updates = debezium_parser.iter_updates()

    await anext(updates)
    await updates.aclose()

    assert fake.events == ["start", "message 1", "stop"]


async def test_iter_updates_ends_silently_on_failure_mid_stream_current_behaviour(
    consumer,
    caplog,
):
    fake = consumer(
        [_message(before=None, after=_note_payload(), offset=7)],
        fail_with=errors.KafkaError("broker down"),
    )

    records = [record async for record in debezium_parser.iter_updates()]

    assert [record.note_id for record in records] == [NOTE_ID]
    assert fake.events == ["start", "message 7", "commit", "stop"]
    [message] = _error_messages(caplog)
    assert message.startswith(
        "Error consuming the message: topic=cache-notes-test, offset=7\nvalue=",
    )


async def test_iter_updates_ends_silently_on_unparsable_message_current_behaviour(
    consumer,
    caplog,
):
    broken = _message(before=None, after=None, offset=3)
    broken.value = b"not json"
    fake = consumer(
        [broken, _message(before=None, after=_note_payload(), offset=4)],
    )

    records = [record async for record in debezium_parser.iter_updates()]

    assert records == []
    assert fake.events == ["start", "message 3", "stop"]
    assert _error_messages(caplog) == [
        "Error consuming the message: topic=cache-notes-test, offset=3\n"
        "value=b'not json'",
    ]


@pytest.mark.xfail(
    strict=True,
    raises=UnboundLocalError,
    reason=(
        "BUG: kafka/debezium_parser.py:88 the except block reads `msg`, which is unbound "
        "when the consumer fails before the first message"
    ),
)
async def test_iter_updates_failure_before_first_message_is_reported(consumer):
    fake = consumer([], fail_with=errors.KafkaError("broker down"))

    try:
        records = [record async for record in debezium_parser.iter_updates()]
    except errors.KafkaError:
        records = []

    assert records == []
    assert fake.events == ["start", "stop"]


async def test_iter_updates_stops_consumer_when_first_message_fails(consumer):
    fake = consumer([], fail_with=errors.KafkaError("broker down"))

    with pytest.raises(Exception):  # noqa: B017, PT011
        [record async for record in debezium_parser.iter_updates()]

    assert fake.events == ["start", "stop"]


async def test_iter_updates_start_failure_leaves_consumer_unstopped_current_behaviour(
    consumer,
):
    fake = consumer([])
    fake.start.side_effect = errors.KafkaConnectionError("down")

    with pytest.raises(errors.KafkaConnectionError):
        [record async for record in debezium_parser.iter_updates()]

    fake.stop.assert_not_awaited()
    fake.commit.assert_not_awaited()


async def test_to_notify_sends_note_id(repeat_note):
    await debezium_parser._to_notify(Record(after=_note_payload()))

    repeat_note.assert_awaited_once_with(NOTE_ID)


@pytest.mark.parametrize(
    "make_record",
    [
        lambda: Record(after=_note_payload(is_deleted=True), before=_note_payload()),
        lambda: Record(after=None, before=_note_payload()),
        lambda: Record(after=None),
    ],
    ids=["soft-delete", "hard-delete", "empty"],
)
async def test_to_notify_skips_deleted_note(repeat_note, make_record):
    await debezium_parser._to_notify(make_record())

    repeat_note.assert_not_awaited()


async def test_to_notify_propagates_kafka_failure(repeat_note):
    repeat_note.side_effect = kafka.KafkaSendError("broker down")

    with pytest.raises(kafka.KafkaSendError, match="broker down"):
        await debezium_parser._to_notify(Record(after=_note_payload()))


@pytest.mark.parametrize(
    "make_record",
    [
        lambda: Record(after=_note_payload(content="Новый текст")),
        lambda: Record(
            after=_note_payload(content="Новый текст"),
            before=_note_payload(content="old"),
        ),
    ],
    ids=["insert", "update"],
)
async def test_to_search_engine_updates_content(search_engine, make_record):
    await debezium_parser._to_search_engine(make_record())

    search_engine.update_content.assert_awaited_once_with(
        note_id=NOTE_ID,
        content="Новый текст",
        added_at=ADDED_AT,
    )
    search_engine.delete.assert_not_awaited()


@pytest.mark.parametrize(
    "make_record",
    [
        lambda: Record(after=_note_payload(is_deleted=True), before=_note_payload()),
        lambda: Record(after=None, before=_note_payload()),
    ],
    ids=["soft-delete", "hard-delete"],
)
async def test_to_search_engine_deletes_note(search_engine, make_record):
    await debezium_parser._to_search_engine(make_record())

    search_engine.delete.assert_awaited_once_with(NOTE_ID)
    search_engine.update_content.assert_not_awaited()


async def test_to_search_engine_fails_on_record_without_note(search_engine):
    with pytest.raises(ValueError, match="Note id not found"):
        await debezium_parser._to_search_engine(Record(after=None))

    search_engine.delete.assert_not_awaited()
    search_engine.update_content.assert_not_awaited()


@pytest.fixture
def two_records(mocker) -> dict:
    records = [
        Record(after=_note_payload(note_id=NOTE_ID)),
        Record(after=_note_payload(note_id=OTHER_NOTE_ID)),
    ]
    state = {"records": records, "closed": False}

    async def _iter_updates():
        try:
            for record in records:
                yield record
        finally:
            state["closed"] = True

    mocker.patch.object(debezium_parser, "iter_updates", _iter_updates)
    return state


@pytest.fixture
def to_search_engine(mocker):
    return mocker.patch.object(debezium_parser, "_to_search_engine", mocker.AsyncMock())


async def test_parse_indexes_and_notifies_every_record_when_enabled(
    two_records,
    repeat_note,
    to_search_engine,
    mocker,
):
    mocker.patch.object(settings, "EX_ENABLE_KAFKA_TO_NOTIFY", True)

    await debezium_parser.parse()

    assert to_search_engine.await_args_list == [
        mocker.call(record) for record in two_records["records"]
    ]
    assert repeat_note.await_args_list == [
        mocker.call(NOTE_ID),
        mocker.call(OTHER_NOTE_ID),
    ]
    assert two_records["closed"] is True


async def test_parse_only_indexes_when_notification_is_disabled(
    two_records,
    repeat_note,
    to_search_engine,
    mocker,
):
    mocker.patch.object(settings, "EX_ENABLE_KAFKA_TO_NOTIFY", False)

    await debezium_parser.parse()

    assert to_search_engine.await_count == 2
    repeat_note.assert_not_awaited()


async def test_parse_indexes_before_notifying(
    two_records,
    repeat_note,
    to_search_engine,
    mocker,
):
    mocker.patch.object(settings, "EX_ENABLE_KAFKA_TO_NOTIFY", True)
    manager = mocker.Mock()
    manager.attach_mock(to_search_engine, "index")
    manager.attach_mock(repeat_note, "notify")

    await debezium_parser.parse()

    assert [call[0] for call in manager.mock_calls] == [
        "index",
        "notify",
        "index",
        "notify",
    ]


async def test_parse_stops_on_notify_failure_and_closes_the_stream(
    two_records,
    repeat_note,
    to_search_engine,
    mocker,
):
    mocker.patch.object(settings, "EX_ENABLE_KAFKA_TO_NOTIFY", True)
    repeat_note.side_effect = kafka.KafkaSendError("broker down")

    with pytest.raises(kafka.KafkaSendError):
        await debezium_parser.parse()

    to_search_engine.assert_awaited_once_with(two_records["records"][0])
    assert two_records["closed"] is True


async def test_parse_stops_on_search_engine_failure_without_notifying(
    two_records,
    repeat_note,
    to_search_engine,
    mocker,
):
    mocker.patch.object(settings, "EX_ENABLE_KAFKA_TO_NOTIFY", True)
    to_search_engine.side_effect = manticoresearch.ManticoreException("down")

    with pytest.raises(manticoresearch.ManticoreException):
        await debezium_parser.parse()

    repeat_note.assert_not_awaited()
    assert two_records["closed"] is True


async def test_parse_does_not_commit_the_record_it_failed_on(
    consumer,
    search_engine,
    mocker,
):
    mocker.patch.object(settings, "EX_ENABLE_KAFKA_TO_NOTIFY", False)
    fake = consumer(
        [
            _message(before=None, after=_note_payload(), offset=1),
            _message(before=None, after=_note_payload(note_id=OTHER_NOTE_ID), offset=2),
        ],
    )
    search_engine.update_content.side_effect = [
        None,
        manticoresearch.ManticoreException("down"),
    ]

    with pytest.raises(manticoresearch.ManticoreException):
        await debezium_parser.parse()

    assert fake.events == ["start", "message 1", "commit", "message 2", "stop"]
