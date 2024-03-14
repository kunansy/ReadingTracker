import uuid
from collections.abc import Callable, Coroutine
from functools import wraps
from typing import Any

from aiokafka import AIOKafkaProducer

from tracker.common import logger, settings


FUNC_TYPE = Callable[[], Coroutine[Any, Any, AIOKafkaProducer]]


def cache(func: FUNC_TYPE) -> FUNC_TYPE:
    producer: AIOKafkaProducer | None = None

    @wraps(func)
    async def wrapped(*args: Any, **kwargs: Any) -> AIOKafkaProducer:
        nonlocal producer
        if not producer:
            producer = await func(*args, **kwargs)
        return producer

    return wrapped


@cache
async def _producer() -> AIOKafkaProducer:
    return AIOKafkaProducer(
        bootstrap_servers=settings.KAFKA_URL,
        enable_idempotence=True,
    )


async def _send_one(key: str, value: str, *, topic: str) -> None:
    producer = await _producer()
    await producer.start()

    try:
        logger.logger.debug(
            "Sending a message: key=%s, value=%s, to %s",
            key,
            value,
            topic,
        )
        await producer.send_and_wait(topic, key=key.encode(), value=value.encode())
    except aiokafka.errors.KafkaError:
        logger.logger.exception("Could not send message")
    else:
        logger.logger.debug("Message sent")
    finally:
        await producer.stop()


async def repeat_note(note_id: uuid.UUID | str) -> None:
    await _send_one("note_id", str(note_id), topic=settings.KAFKA_REPEAT_NOTES_TOPIC)
