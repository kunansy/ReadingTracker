import asyncio

from aiokafka import AIOKafkaProducer


async def send_one():
    producer = AIOKafkaProducer(
        bootstrap_servers="127.0.0.1:9092",
        enable_idempotence=True,
    )
    await producer.start()

    try:
        await producer.send_and_wait("notifies", key=b"ghjfg34r", value=b"42")
    finally:
        await producer.stop()


asyncio.run(send_one())
