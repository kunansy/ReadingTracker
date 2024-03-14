from collections.abc import AsyncIterable
from functools import lru_cache

import orjson
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from tracker.common import settings, kafka
from tracker.common.logger import logger


async def iter_updates() -> AsyncIterable[tuple[dict | None, dict]]:
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
            yield payload["before"], payload["after"]
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