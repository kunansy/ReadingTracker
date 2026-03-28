import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from aiokafka import AIOKafkaProducer, errors

from tracker.common import logger, settings


@asynccontextmanager
async def _kafka_producer() -> AsyncIterator[AIOKafkaProducer]:
    producer = AIOKafkaProducer(
        bootstrap_servers=settings.KAFKA_URL,
        enable_idempotence=True,
    )
    async with asyncio.timeout(settings.KAFKA_CONNECT_TIMEOUT):
        await producer.start()

    try:
        yield producer
    except errors.KafkaError:
        logger.exception("Error with kafka producer")
    finally:
        async with asyncio.timeout(settings.KAFKA_CONNECT_TIMEOUT):
            await producer.stop()


async def _send_one(key: str, value: str, *, topic: str) -> None:
    async with _kafka_producer() as producer:
        try:
            logger.debug(
                "Sending a message: key=%s, value=%s, to %s",
                key,
                value,
                topic,
            )
            await producer.send_and_wait(topic, key=key.encode(), value=value.encode())
        except errors.KafkaError:
            logger.exception("Could not send message")
        else:
            logger.debug("Message sent")


async def repeat_note(note_id: uuid.UUID | str) -> None:
    await _send_one("note_id", str(note_id), topic=settings.KAFKA_REPEAT_NOTES_TOPIC)
