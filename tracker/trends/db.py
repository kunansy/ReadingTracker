import asyncio
import datetime
from decimal import Decimal
from typing import NamedTuple

import sqlalchemy.sql as sa

from tracker.common.log import logger
from tracker.models import models
from tracker.common import database


class WeekBoard(NamedTuple):
    start: datetime.date
    stop: datetime.date


class Trend(NamedTuple):
    week: WeekBoard
    last_week_value: Decimal
    current_week_value: Decimal
    trend: Decimal


def _get_last_week_range() -> WeekBoard:
    now = datetime.date.today()
    weekday = now.weekday()

    start = now - datetime.timedelta(days=weekday + 7)
    stop = start + datetime.timedelta(days=weekday)

    return WeekBoard(start=start, stop=stop)


def _get_current_week_range() -> WeekBoard:
    now = datetime.date.today()
    weekday = now.weekday()

    start = now - datetime.timedelta(days=weekday)

    return WeekBoard(start=start, stop=now)


async def _get_week_read_pages(week: WeekBoard) -> Decimal:
    logger.debug("Getting week='%s' read pages", week)
    start, stop = week

    stmt = sa.select(sa.func.sum(models.ReadingLog.c.count)) \
        .where(sa.func.date(models.ReadingLog.c.date) >= start) \
        .where(sa.func.date(models.ReadingLog.c.date) <= stop)

    async with database.session() as ses:
        value = await ses.scalar(stmt)

    logger.debug("Week='%s' read pages got", week)
    return Decimal(value)


async def _get_week_inserted_notes(week: WeekBoard) -> Decimal:
    logger.debug("Getting week='%s' inserted notes count", week)
    start, stop = week

    stmt = sa.select(sa.func.count(models.Notes.c.note_id)) \
        .where(sa.func.date(models.Notes.c.added_at) >= start) \
        .where(sa.func.date(models.Notes.c.added_at) <= stop)

    async with database.session() as ses:
        value = await ses.scalar(stmt)

    logger.debug("Week='%s' inserted notes count got", week)
    return Decimal(value)


def _calculate_trend(*,
                     last_week_value: Decimal,
                     current_week_value: Decimal,
                     week: WeekBoard) -> Trend:
    trend = (current_week_value - last_week_value) / last_week_value
    trend_percent: Decimal = round(trend * 100, 2) # type: ignore

    return Trend(
        week=week,
        last_week_value=last_week_value,
        current_week_value=current_week_value,
        trend=trend_percent
    )


async def get_read_pages_trend() -> Trend:
    logger.info("Getting read pages trend")

    last_week, current_week = _get_last_week_range(), _get_current_week_range()

    last_week_read_pages_task = asyncio.create_task(_get_week_read_pages(last_week))
    current_week_read_pages_task = asyncio.create_task(_get_week_read_pages(current_week))

    await last_week_read_pages_task
    await current_week_read_pages_task

    trend = _calculate_trend(
        last_week_value=last_week_read_pages_task.result(),
        current_week_value=current_week_read_pages_task.result(),
        week=current_week
    )

    logger.info("Reading pages trend got")
    return trend


async def get_inserted_notes_trend() -> Trend:
    logger.info("Getting inserted notes trend")

    last_week, current_week = _get_last_week_range(), _get_current_week_range()

    last_week_inserted_notes_task = asyncio.create_task(_get_week_inserted_notes(last_week))
    current_week_inserted_notes_task = asyncio.create_task(_get_week_inserted_notes(current_week))

    await last_week_inserted_notes_task
    await current_week_inserted_notes_task

    trend = _calculate_trend(
        last_week_value=last_week_inserted_notes_task.result(),
        current_week_value=current_week_inserted_notes_task.result(),
        week=current_week
    )

    logger.info("Inserted notes trend got")
    return trend
