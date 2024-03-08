import asyncio

from aiokafka import AIOKafkaConsumer


async def consume():
    consumer = AIOKafkaConsumer(
        "notifies",
        bootstrap_servers="127.0.0.1:9092",
        group_id="telegram_bot",
        enable_auto_commit=False,
    )

    await consumer.start()
    try:
        msg = await consumer.getone()
        # async for msg in consumer:
        print("consumed: ", msg.topic, msg.partition, msg.offset,
              msg.key, msg.value, msg.timestamp)

        await consumer.commit()
    finally:
        await consumer.stop()


asyncio.run(consume())
