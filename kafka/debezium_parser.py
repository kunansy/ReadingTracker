from collections.abc import AsyncIterable
from functools import lru_cache

import orjson
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from tracker.common import settings, kafka
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
        group_id="parse_debezium",
        request_timeout_ms=1000,
        auto_offset_reset="earliest",
        # TODO
        enable_auto_commit=False
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


async def _to_notes_cache(payload: dict) -> None:
    pass


async def _to_notify(payload: dict) -> None:
    pass


async def _to_search_engine(payload: dict) -> None:
    pass


async def parse():
    async for _, after in iter_updates():
        print(after)
        await _to_notes_cache(after)
        await _to_notify(after)
        await _to_search_engine(after)


import asyncio
asyncio.run(parse())