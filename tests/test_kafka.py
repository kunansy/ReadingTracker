import logging

import pytest
from aiokafka import errors

from tracker.common import kafka, settings


@pytest.fixture
def producer(mocker):
    producer = mocker.MagicMock()
    producer.start = mocker.AsyncMock()
    producer.stop = mocker.AsyncMock()
    producer.send_and_wait = mocker.AsyncMock()
    mocker.patch.object(kafka, "AIOKafkaProducer", return_value=producer)
    return producer


async def test_repeat_note_sends_message(producer):
    await kafka.repeat_note("note-id")

    producer.send_and_wait.assert_awaited_once()
    producer.stop.assert_awaited_once()


async def test_repeat_note_raises_when_send_fails(producer):
    producer.send_and_wait.side_effect = errors.KafkaError("boom")

    with pytest.raises(kafka.KafkaSendError):
        await kafka.repeat_note("note-id")

    producer.stop.assert_awaited_once()


async def test_send_failure_is_left_to_the_caller_to_log(producer, caplog):
    producer.send_and_wait.side_effect = errors.KafkaError("boom")

    with pytest.raises(kafka.KafkaSendError):
        await kafka.repeat_note("note-id")

    assert not [
        r
        for r in caplog.records
        if r.name == settings.LOGGER_NAME and r.levelno >= logging.ERROR
    ]


async def test_repeat_note_raises_when_broker_is_unreachable(producer):
    producer.start.side_effect = errors.KafkaConnectionError("down")

    with pytest.raises(kafka.KafkaSendError):
        await kafka.repeat_note("note-id")

    producer.send_and_wait.assert_not_awaited()


async def test_stop_failure_does_not_mask_send_error(producer):
    producer.send_and_wait.side_effect = errors.KafkaError("boom")
    producer.stop.side_effect = errors.KafkaError("stop failed")

    with pytest.raises(kafka.KafkaSendError):
        await kafka.repeat_note("note-id")
