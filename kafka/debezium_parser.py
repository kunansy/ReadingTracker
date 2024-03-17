import asyncio
from collections.abc import AsyncIterable

import orjson
from aiokafka import AIOKafkaConsumer
from pydantic import field_validator

from tracker.common import kafka, manticoresearch, redis_api, settings
from tracker.common.logger import logger
from tracker.common.schemas import CustomBaseModel
from tracker.notes.db import Note


class Record(CustomBaseModel):
    after: Note
    before: Note | None = None

    @field_validator("after", mode="before")
    def validate_after(cls, after: dict | None) -> dict | None:
        if not after:
            return None
        after["added_at"] //= 1_000
        return after

    def is_insert(self) -> bool:
        return self.after is not None and self.before is None

    def is_update(self) -> bool:
        return self.after is not None and self.before is not None

    def is_delete(self) -> bool:
        return self.after.is_deleted

    def dump_after(self) -> dict:
        return self.after.model_dump(mode="json", exclude_none=True)


async def iter_updates() -> AsyncIterable[Record]:
    consumer = AIOKafkaConsumer(
        settings.KAFKA_CACHE_NOTES_TOPIC,
        bootstrap_servers=settings.KAFKA_URL,
        group_id="parse_debezium",
        request_timeout_ms=1000,
        auto_offset_reset="earliest",
        # TODO
        enable_auto_commit=False,
    )

    await consumer.start()

    try:
        async for msg in consumer:
            payload = orjson.loads(msg.value)["payload"]
            yield Record(before=payload["before"], after=payload["after"])
    except Exception:
        logger.exception("")
    finally:
        await consumer.stop()


async def _to_notes_cache(payload: Note) -> None:
    logger.info("To cache: note_id=%s", payload.note_id)

    if payload.is_deleted:
        logger.info("Deleting the note")
        await redis_api.delete_note(payload.note_id)
    else:
        logger.info("Updating the note")
        await redis_api.set_note(payload.model_dump(mode="json", exclude_none=True))


async def _to_notify(payload: Note) -> None:
    if payload.is_deleted:
        logger.info("The note has been deleted, don't notify")
        return
    logger.info("To notify: note_id=%s", payload.note_id)
    await kafka.repeat_note(payload.note_id)
    logger.info("Sent")


async def _to_search_engine(payload: Note) -> None:
    logger.info("To search engine: note_id=%s", payload.note_id)
    if payload.is_deleted:
        logger.info("Delete the note")
        return await manticoresearch.delete(payload.note_id)

    logger.info("Update the note")
    return await manticoresearch.update_content(
        note_id=payload.note_id,
        content=payload.content,
        added_at=payload.added_at,
    )


async def parse():
    async for msg in iter_updates():
        payload = msg.after
        await _to_notes_cache(payload)
        await _to_notify(payload)
        await _to_search_engine(payload)


asyncio.run(parse())
