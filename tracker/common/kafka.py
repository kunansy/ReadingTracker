import uuid

import aiokafka

from tracker.common import logger, settings


async def _producer() -> aiokafka.AIOKafkaProducer:
    producer: aiokafka.AIOKafkaProducer | None = None

    async def wrapper() -> aiokafka.AIOKafkaProducer:
        nonlocal producer
        if not producer:
            producer = aiokafka.AIOKafkaProducer(
                bootstrap_servers=settings.KAFKA_URL,
                enable_idempotence=True,
            )
        return producer

    return await wrapper()


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
