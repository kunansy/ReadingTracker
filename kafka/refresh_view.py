import asyncio

import sqlalchemy.sql as sa

from tracker.common import database, logger


REFRESH_REPEAT_NOTES_STMT = sa.text("REFRESH MATERIALIZED VIEW mvw_repeat_notes;")


async def refresh_view():
    logger.info("Refreshing the view")

    async with database.session() as ses:
        await ses.execute(REFRESH_REPEAT_NOTES_STMT)

    logger.info("View refreshed")


asyncio.run(refresh_view())
