import uuid

from aiokafka import AIOKafkaProducer, errors

from tracker.common import logger, settings


async def _send_one(key: str, value: str, *, topic: str) -> None:
    # TODO: create one in the context manager
    producer = AIOKafkaProducer(
        bootstrap_servers=settings.KAFKA_URL,
        enable_idempotence=True,
    )
    await producer.start()

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
    finally:
        await producer.stop()


async def repeat_note(note_id: uuid.UUID | str) -> None:
    await _send_one("note_id", str(note_id), topic=settings.KAFKA_REPEAT_NOTES_TOPIC)
