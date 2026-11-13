import asyncio
import logging
from uuid import UUID

import pytest
from aiokafka import errors

from tracker.common import kafka, settings


NOTE_ID = UUID("018e9dbe-1d3d-7a5a-b437-9bfa65171b42")


@pytest.fixture
def producer(mocker):
    producer = mocker.MagicMock()
    producer.start = mocker.AsyncMock()
    producer.stop = mocker.AsyncMock()
    producer.send_and_wait = mocker.AsyncMock()
    producer.factory = mocker.patch.object(
        kafka,
        "AIOKafkaProducer",
        return_value=producer,
    )
    return producer


async def _hang() -> None:
    await asyncio.Event().wait()


def _error_records(caplog) -> list[logging.LogRecord]:
    return [
        record
        for record in caplog.records
        if record.name == settings.LOGGER_NAME and record.levelno >= logging.ERROR
    ]


async def test_repeat_note_sends_note_id_to_the_repeat_topic(producer):
    await kafka.repeat_note(NOTE_ID)

    producer.factory.assert_called_once_with(
        bootstrap_servers="127.0.0.1:1",
        enable_idempotence=True,
    )
    producer.start.assert_awaited_once_with()
    producer.send_and_wait.assert_awaited_once_with(
        "repeat-notes-test",
        key=b"note_id",
        value=b"018e9dbe-1d3d-7a5a-b437-9bfa65171b42",
    )
    producer.stop.assert_awaited_once_with()


async def test_repeat_note_accepts_string_id(producer):
    await kafka.repeat_note("note-id")

    producer.send_and_wait.assert_awaited_once_with(
        "repeat-notes-test",
        key=b"note_id",
        value=b"note-id",
    )


async def test_send_one_encodes_unicode_as_utf8(producer):
    await kafka._send_one("ключ", "значение 🙂", topic="topic")

    producer.send_and_wait.assert_awaited_once_with(
        "topic",
        key="ключ".encode(),
        value="значение 🙂".encode(),
    )


async def test_producer_is_started_before_and_stopped_after_sending(producer, mocker):
    manager = mocker.Mock()
    manager.attach_mock(producer.start, "start")
    manager.attach_mock(producer.send_and_wait, "send_and_wait")
    manager.attach_mock(producer.stop, "stop")

    await kafka.repeat_note("note-id")

    assert [call[0] for call in manager.mock_calls] == ["start", "send_and_wait", "stop"]


async def test_repeat_note_raises_when_send_fails(producer):
    error = errors.KafkaError("boom")
    producer.send_and_wait.side_effect = error

    with pytest.raises(kafka.KafkaSendError) as exc_info:
        await kafka.repeat_note("note-id")

    assert str(exc_info.value) == (
        "Could not send message to repeat-notes-test: KafkaError('boom')"
    )
    assert exc_info.value.__cause__ is error
    producer.stop.assert_awaited_once_with()


async def test_send_failure_is_left_to_the_caller_to_log(producer, caplog):
    producer.send_and_wait.side_effect = errors.KafkaError("boom")

    with pytest.raises(kafka.KafkaSendError):
        await kafka.repeat_note("note-id")

    assert _error_records(caplog) == []


async def test_non_kafka_send_error_propagates_and_producer_is_stopped(producer):
    producer.send_and_wait.side_effect = ValueError("bad value")

    with pytest.raises(ValueError, match="bad value"):
        await kafka.repeat_note("note-id")

    producer.stop.assert_awaited_once_with()


async def test_repeat_note_raises_when_broker_is_unreachable(producer):
    error = errors.KafkaConnectionError("down")
    producer.start.side_effect = error

    with pytest.raises(kafka.KafkaSendError) as exc_info:
        await kafka.repeat_note("note-id")

    assert str(exc_info.value).startswith(
        "Could not connect to kafka: KafkaConnectionError"
    )
    assert exc_info.value.__cause__ is error
    producer.send_and_wait.assert_not_awaited()
    producer.stop.assert_awaited_once_with()


async def test_repeat_note_raises_when_start_raises_timeout(producer):
    producer.start.side_effect = TimeoutError()

    with pytest.raises(kafka.KafkaSendError) as exc_info:
        await kafka.repeat_note("note-id")

    assert str(exc_info.value) == "Could not connect to kafka: TimeoutError()"
    producer.send_and_wait.assert_not_awaited()
    producer.stop.assert_awaited_once_with()


async def test_repeat_note_raises_when_connect_exceeds_the_timeout(producer, mocker):
    mocker.patch.object(settings, "KAFKA_CONNECT_TIMEOUT", 0)
    producer.start.side_effect = _hang

    with pytest.raises(kafka.KafkaSendError, match="Could not connect to kafka"):
        await kafka.repeat_note("note-id")

    producer.send_and_wait.assert_not_awaited()
    producer.stop.assert_awaited_once_with()


async def test_other_start_error_leaves_producer_unstopped_current_behaviour(producer):
    producer.start.side_effect = OSError("no route to host")

    with pytest.raises(OSError, match="no route to host"):
        await kafka.repeat_note("note-id")

    producer.send_and_wait.assert_not_awaited()
    producer.stop.assert_not_awaited()


async def test_stop_failure_after_connect_failure_is_suppressed(producer, caplog):
    producer.start.side_effect = errors.KafkaConnectionError("down")
    producer.stop.side_effect = errors.KafkaError("stop failed")

    with pytest.raises(kafka.KafkaSendError, match="Could not connect"):
        await kafka.repeat_note("note-id")

    assert [r.getMessage() for r in _error_records(caplog)] == [
        "Could not stop kafka producer",
    ]


async def test_stop_failure_does_not_mask_send_error(producer, caplog):
    producer.send_and_wait.side_effect = errors.KafkaError("boom")
    producer.stop.side_effect = errors.KafkaError("stop failed")

    with pytest.raises(kafka.KafkaSendError, match="Could not send"):
        await kafka.repeat_note("note-id")

    assert [r.getMessage() for r in _error_records(caplog)] == [
        "Could not stop kafka producer",
    ]


@pytest.mark.parametrize(
    "error",
    [errors.KafkaError("stop failed"), TimeoutError()],
    ids=["kafka-error", "timeout"],
)
async def test_stop_failure_after_successful_send_is_swallowed(producer, caplog, error):
    producer.stop.side_effect = error

    await kafka.repeat_note("note-id")

    producer.send_and_wait.assert_awaited_once()
    assert [r.getMessage() for r in _error_records(caplog)] == [
        "Could not stop kafka producer",
    ]


async def test_stop_that_exceeds_the_timeout_is_swallowed(producer, mocker, caplog):
    mocker.patch.object(settings, "KAFKA_CONNECT_TIMEOUT", 0)
    producer.stop.side_effect = _hang

    await kafka._stop(producer)

    producer.stop.assert_awaited_once_with()
    assert [r.getMessage() for r in _error_records(caplog)] == [
        "Could not stop kafka producer",
    ]


async def test_stop_does_not_swallow_other_errors(producer):
    producer.stop.side_effect = RuntimeError("unexpected")

    with pytest.raises(RuntimeError, match="unexpected"):
        await kafka._stop(producer)
