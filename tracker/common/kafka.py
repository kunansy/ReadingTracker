import asyncio
import uuid

import aiokafka

from tracker.common import logger, settings


_PRODUCER = aiokafka.AIOKafkaProducer(
    bootstrap_servers=settings.KAFKA_URL,
    enable_idempotence=True,
)


async def _send_one(key: str, value: str, *, topic: str) -> None:
    await _PRODUCER.start()

    try:
        logger.logger.debug("Sending a message: key=%s, value=%s, to %s", key, value, topic)
        await _PRODUCER.send_and_wait(topic, key=key.encode(), value=value.encode())
    except aiokafka.errors.KafkaError:
        logger.logger.exception("Could not send message")
    else:
        logger.logger.debug("Message sent")
    finally:
        await _PRODUCER.stop()


async def repeat_note(note_id: uuid.UUID | str) -> None:
    await _send_one("note_id", note_id, topic=settings.KAFKA_REPEAT_NOTES_TOPIC)
