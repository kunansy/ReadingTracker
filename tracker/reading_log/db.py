import asyncio
import datetime
from collections import defaultdict
from collections.abc import AsyncGenerator
from typing import cast
from uuid import UUID

import sqlalchemy.sql as sa

from tracker.common import database
from tracker.common.logger import logger
from tracker.common.schemas import CustomBaseModel
from tracker.materials import db as materials_db
from tracker.models import models


class LogRecord(CustomBaseModel):
    log_id: UUID | None = None
    date: datetime.date
    count: int
    material_id: UUID
    material_title: str | None = None


def _safe_list_get[T](lst: list[T], index: int, default: T | None = None) -> T | None:
    try:
        return lst[index]
    except IndexError:
        return default


async def list_log_records(
    *,
    material_id: UUID | None = None,
    from_date: datetime.date | None = None,
    to_date: datetime.date | None = None,
) -> list[LogRecord]:
    logger.debug("Getting all log records")

    stmt = sa.select(models.ReadingLog).order_by(models.ReadingLog.c.date.desc())

    if material_id:
        stmt = stmt.where(models.ReadingLog.c.material_id == str(material_id))
    if from_date:
        stmt = stmt.where(from_date <= models.ReadingLog.c.date)
    if to_date:
        stmt = stmt.where(to_date >= models.ReadingLog.c.date)

    async with database.session() as ses:
        records = [
            LogRecord.model_validate(row, from_attributes=True)
            for row in (await ses.execute(stmt)).all()
        ]

    logger.debug("%s log records got", len(records))
    return records


async def get_log_record(*, log_id: UUID) -> LogRecord:
    logger.debug("Getting log record, id=%s", log_id)

    stmt = sa.select(models.ReadingLog).where(models.ReadingLog.c.log_id == str(log_id))

    async with database.session() as ses:
        if row := (await ses.execute(stmt)).one_or_none():
            logger.debug("Record got")
            return LogRecord.model_validate(row, from_attributes=True)

    msg = f"Log record id={log_id!r} not found"
    logger.info(msg)
    raise database.NotFoundException(msg)


async def get_completion_dates() -> dict[UUID | None, datetime.datetime]:
    logger.debug("Getting completion dates")

    stmt = (
        sa.select(models.Materials.c.material_id, models.Statuses.c.completed_at)
        .join(
            models.Statuses,
            models.Materials.c.material_id == models.Statuses.c.material_id,
        )
        .where(models.Statuses.c.completed_at != None)
    )

    async with database.session() as ses:
        dates = {  # noqa: C416
            material_id: completed_at
            for material_id, completed_at in (await ses.execute(stmt)).all()
        }

    logger.debug("%s completion dates got", len(dates))
    return dates


async def data(
    *,
    log_records: list[LogRecord] | None = None,
    completion_dates: dict[UUID | None, datetime.datetime] | None = None,
) -> AsyncGenerator[tuple[datetime.date, LogRecord]]:
    """Get pairs: (date, info) of all days from start to stop.

    If the day is empty, material_id is supposed
    as the material_id of the last not empty day.
    """
    logger.debug("Getting logging data")

    if not (log_records := log_records or await list_log_records()):
        return

    log_records_dict: defaultdict[datetime.date, list[LogRecord]] = defaultdict(list)
    for log_record in log_records:
        log_records_dict[log_record.date].append(log_record)

    # stack for materials
    materials: list[UUID] = []
    try:
        completion_dates = completion_dates or await get_completion_dates()
    except Exception as e:
        logger.exception(e)
        completion_dates = {}

    step = datetime.timedelta(days=1)
    iter_over_dates = min(log_records_dict.keys())

    while iter_over_dates <= database.utcnow().date():
        last_material_id = _safe_list_get(materials, -1, None)

        # several materials might be completed the one day
        completion_date = completion_dates.get(last_material_id)
        while completion_date and completion_date.date() < iter_over_dates:
            materials.pop()
            last_material_id = _safe_list_get(materials, -1, None)
            completion_date = completion_dates.get(last_material_id)

        if not (log_records_ := log_records_dict.get(iter_over_dates)):
            log_record = LogRecord(
                material_id=cast("UUID", last_material_id),
                count=0,
                date=iter_over_dates,
            )

            yield iter_over_dates, log_record
            iter_over_dates += step
        else:
            for log_record in log_records_:
                material_id = log_record.material_id

                if not (materials and material_id in materials):
                    # new material started, the last one completed
                    materials.append(material_id)
                elif material_id != last_material_id:
                    # in this case several materials
                    # are being reading one by one
                    materials.remove(material_id)
                    materials.append(material_id)
                    # if several materials have read in one day
                    last_material_id = material_id

                yield iter_over_dates, log_record
            iter_over_dates += step


async def is_log_empty() -> bool:
    logger.debug("Checking the log is empty")
    stmt = sa.select(sa.func.count(1) == 0).select_from(models.ReadingLog)  # type: ignore[arg-type]

    async with database.session() as ses:
        is_empty = await ses.scalar(stmt)

    if is_empty is None:
        is_empty = True

    logger.debug("Log empty: %s", is_empty)
    return is_empty


async def get_material_reading_now() -> UUID | None:
    logger.debug("Getting material reading now")

    if await is_log_empty():
        logger.warning("Reading log is empty, no materials reading")
        return None

    last_material_id = None
    async for _, info in data():
        last_material_id = info.material_id

    if last_material_id is not None:
        logger.debug("Now %s is reading", last_material_id)
        return last_material_id

    logger.debug("Reading material not found")

    # to resolve circular import
    from tracker.materials import db as materials_db

    # means the new material started
    #  and there's no log records for it
    material_id = await materials_db.get_last_material_started()
    logger.debug("So, assume the last inserted material is reading: %s", material_id)

    return material_id


async def insert_log_record(
    *,
    material_id: str | UUID,
    count: int,
    date: datetime.date,
) -> UUID:
    logger.debug(
        "Inserting log material_id=%s, count=%s, date=%s",
        material_id,
        count,
        date,
    )

    values = {"material_id": str(material_id), "count": count, "date": date}
    stmt = models.ReadingLog.insert().values(values).returning(models.ReadingLog.c.log_id)

    async with database.session() as ses:
        log_id = await ses.scalar(stmt)

    logger.debug("Log record inserted, id=%s", log_id)
    return cast("UUID", log_id)


async def check_record_correct(
    *,
    material_id: UUID,
    date: datetime.date,
    count: int,
) -> None:
    if date > database.utcnow().date():
        raise ValueError("Date could not be in the future")
    if count <= 0:
        raise ValueError("Count must be greater than 0")

    async with asyncio.TaskGroup() as tg:
        reading_materials_task = tg.create_task(materials_db.get_reading_materials())
        log_records_task = tg.create_task(list_log_records(material_id=material_id))

    materials = [
        material
        for material in reading_materials_task.result()
        if material.material_id == material_id
    ]
    if not materials:
        raise ValueError(f"No reading material id={material_id} found")
    material = materials[0]

    st = material.status
    if date < st.started_at.date() or (st.completed_at and date > st.completed_at.date()):
        raise ValueError(
            "Date is not inside the range. "
            f"{date} not in [{st.started_at}; {st.completed_at}]",
        )

    total_pages_read = sum(record.count for record in log_records_task.result())
    if total_pages_read + count > material.material.pages:
        raise ValueError(
            "There are more pages than the material remains: "
            f"total pages read {total_pages_read}, "
            f"material pages {material.material.pages}",
        )


async def records_sum(
    *,
    from_date: datetime.date | None = None,
    to_date: datetime.date | None = None,
) -> int:
    stmt = sa.select(sa.func.sum(models.ReadingLog.c.count))

    if from_date:
        stmt = stmt.where(from_date <= models.ReadingLog.c.date)
    if to_date:
        stmt = stmt.where(to_date >= models.ReadingLog.c.date)

    async with database.session() as ses:
        return await ses.scalar(stmt) or 0
