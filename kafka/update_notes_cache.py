import asyncio
from collections.abc import AsyncIterable

import orjson
from aiokafka import AIOKafkaConsumer
from pydantic import field_validator

from tracker.common import redis_api, settings
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
        after["added_at"] //= 10_000
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
        group_id="update_notes_cache",
        request_timeout_ms=1000,
        auto_offset_reset="earliest",
    )

    await consumer.start()

    try:
        async for msg in consumer:
            payload = orjson.loads(msg.value)["payload"]
            yield Record(after=payload["after"], before=payload["before"])
    except Exception:
        logger.exception("")
    finally:
        await consumer.stop()


async def update_notes_cache() -> None:
    async for msg in iter_updates():
        note_id = msg.after.note_id

        if msg.is_delete():
            logger.info("Deleting note %s", note_id)
            await redis_api.delete_note(note_id)
        else:
            logger.info("Updating note %s", note_id)
            await redis_api.set_note(msg.dump_after())


asyncio.run(update_notes_cache())
