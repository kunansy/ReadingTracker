import datetime
from typing import NamedTuple, Optional
from uuid import UUID

import sqlalchemy.sql as sa
from sqlalchemy.engine import RowMapping

from tracker.common import database, models
from tracker.common.log import logger
from tracker.reading_log import statistics


class MaterialEstimate(NamedTuple):
    material: RowMapping
    will_be_started: datetime.date
    will_be_completed: datetime.date
    expected_duration: int


class MaterialStatistics(NamedTuple):
    material: RowMapping
    started_at: datetime.date
    duration: int
    lost_time: int
    total: int
    min_record: Optional[database.MinMax]
    max_record: Optional[database.MinMax]
    average: int
    remaining_pages: Optional[int] = None
    remaining_days: Optional[int] = None
    completed_at: Optional[datetime.date] = None
    # date when the material would be completed
    # according to average read pages count
    would_be_completed: Optional[datetime.date] = None


async def get_materials() -> list[RowMapping]:
    logger.info("Getting all materials")

    stmt = sa.select(models.Materials)

    async with database.session() as ses:
        return (await ses.execute(stmt)).all()


async def get_material(*,
                       material_id: UUID) -> Optional[RowMapping]:
    stmt = sa.select(models.Materials)\
        .where(models.Materials.c.material_id == str(material_id))

    async with database.session() as ses:
        return (await ses.execute(stmt)).mappings().one_or_none()


async def _was_material_being_reading(*,
                                      material_id: UUID) -> bool:
    stmt = sa.select(sa.func.count(1) >= 1)\
        .select_from(models.ReadingLog)\
        .where(models.ReadingLog.c.material_id == str(material_id))

    async with database.session() as ses:
        return await ses.scalar(stmt)


async def get_material_statistics(*,
                                  material_id: UUID) -> MaterialStatistics:
    """ Calculate statistics for reading or completed material """
    logger.debug("Calculating statistics for material_id=%s", material_id)

    material = await get_material(material_id=material_id)
    status = await get_status(material_id=material_id)

    assert status is not None
    assert material is not None

    avg_total = await statistics.get_avg_read_pages()
    if await _was_material_being_reading(material_id=material_id):
        log_st = await statistics.get_m_log_statistics(material_id=material_id)
        avg, total = log_st.average, log_st.total
        duration, lost_time = log_st.duration, log_st.lost_time

        max_record, min_record = log_st.max_record, log_st.min_record
    else:
        avg = 1
        total = duration = lost_time = 0
        max_record = min_record = None

    if status.completed_at is None:
        remaining_pages = material.pages - total

        remaining_days = round(remaining_pages / avg)
        if not await _was_material_being_reading(material_id=material_id):
            remaining_days = round(remaining_pages / avg_total)

        would_be_completed = database.today() + datetime.timedelta(days=remaining_days)
    else:
        would_be_completed = remaining_days = remaining_pages = None # type: ignore

    return MaterialStatistics(
        material=material,
        started_at=status.started_at,
        completed_at=status.completed_at,
        duration=duration,
        lost_time=lost_time,
        total=total,
        min_record=min_record,
        max_record=max_record,
        average=avg,
        remaining_pages=remaining_pages,
        remaining_days=remaining_days,
        would_be_completed=would_be_completed
    )


async def processed_statistics() -> list[MaterialStatistics]:
    return [
        await get_material_statistics(material_id=material.material_id)
        for material in await get_completed_materials()
    ]


async def reading_statistics() -> list[MaterialStatistics]:
    return [
        await get_material_statistics(material_id=material.material_id)
        for material in await database.get_reading_materials()
    ]


async def get_title(*,
                    material_id: UUID) -> str:
    logger.info("Getting title for material_id=%s", material_id)

    if material := await get_material(material_id=material_id):
        return material.title

    logger.warning("Material material_id=%s not found", material_id)
    return ''


async def does_material_exist(*,
                              material_id: UUID) -> bool:
    logger.debug("Whether material_id=%s exists", material_id)

    stmt = sa.select(models.Materials.c.material_id)\
        .where(models.Materials.c.material_id == str(material_id))

    async with database.session() as ses:
        return await ses.scalar(stmt) is not None


async def is_material_reading(*,
                              material_id: UUID) -> bool:
    logger.debug("Checking material_id=%s", material_id)

    stmt = sa.select(models.Materials.c.material_id)\
        .join(models.Statuses,
              models.Materials.c.material_id == models.Statuses.c.material_id)\
        .where(models.Statuses.c.started_at != None)\
        .where(models.Statuses.c.completed_at == None)\
        .where(models.Materials.c.material_id == str(material_id))

    async with database.session() as ses:
        return await ses.scalar(stmt) is not None


async def is_material_assigned(*,
                               material_id: UUID) -> bool:
    logger.debug("Checking material_id=%s", material_id)

    stmt = sa.select(models.Materials.c.material_id) \
        .join(models.Statuses,
              models.Materials.c.material_id == models.Statuses.c.material_id) \
        .where(models.Statuses.c.started_at != None) \
        .where(models.Materials.c.material_id == str(material_id))

    async with database.session() as ses:
        return await ses.scalar(stmt) is not None


async def get_free_materials() -> list[RowMapping]:
    logger.debug("Getting free materials")

    assigned_condition = sa.select(1) \
        .select_from(models.Statuses) \
        .where(models.Statuses.c.material_id == models.Materials.c.material_id)

    stmt = sa.select(models.Materials)\
        .where(~sa.exists(assigned_condition)) \

    async with database.session() as ses:
        return (await ses.execute(stmt)).all()


async def get_completed_materials() -> list[RowMapping]:
    logger.debug("Getting completed materials")

    stmt = sa.select([models.Materials,
                      models.Statuses]) \
        .join(models.Statuses,
              models.Materials.c.material_id == models.Statuses.c.material_id) \
        .where(models.Statuses.c.completed_at != None)

    async with database.session() as ses:
        return (await ses.execute(stmt)).mappings().all()


async def get_statuses() -> list[models.Statuses]:
    logger.debug("Getting statuses")

    stmt = sa.select(models.Statuses)

    async with database.session() as ses:
        return (await ses.execute(stmt)).all()


async def get_status(*,
                     material_id: UUID) -> Optional[RowMapping]:
    logger.debug("Getting status for material_id=%s", material_id)

    stmt = sa.select(models.Statuses) \
        .where(models.Statuses.c.material_id == str(material_id))

    async with database.session() as ses:
        return (await ses.execute(stmt)).mappings().one_or_none()


async def add_material(*,
                       title: str,
                       authors: str,
                       pages: int,
                       tags: str) -> None:
    logger.debug("Adding material title=%s", title)

    values = {
        "title": title,
        "authors": authors,
        "pages": pages,
        "tags": tags
    }
    stmt = models.Materials\
        .insert().values(values)

    async with database.session() as ses:
        await ses.execute(stmt)
    logger.debug("Material added")


async def start_material(*,
                         material_id: UUID,
                         start_date: Optional[datetime.date] = None) -> None:
    start_date = start_date or database.today().date()
    logger.debug("Starting material_id=%s", material_id)

    if start_date > database.today().date():
        raise ValueError("Start date must be less than today")

    values = {
        "material_id": str(material_id),
        "started_at": start_date
    }
    stmt = models.Statuses\
        .insert().values(values)

    async with database.session() as ses:
        await ses.execute(stmt)

    logger.debug("Material material_id=%s started", material_id)


async def complete_material(*,
                            material_id: UUID,
                            completion_date: Optional[datetime.date] = None) -> None:
    completion_date = completion_date or database.today().date()
    logger.debug("Completing material_id=%s", material_id)

    get_status_stmt = sa.select(models.Statuses)\
        .where(models.Statuses.c.material_id == str(material_id))

    update_status_stmt = models.Statuses\
        .update().values(completed_at=completion_date)\
        .where(models.Statuses.c.material_id == str(material_id))

    async with database.session() as ses:
        status = (await ses.execute(get_status_stmt)).mappings().first()
        if status is None:
            raise ValueError("Material_id=%s not assigned", material_id)

        if status.completed_at is not None:
            raise ValueError("Material_id=%s even completed", material_id)
        if status.started_at > completion_date:
            raise ValueError

        await ses.execute(update_status_stmt)

    logger.debug("Material_id=%s completed at %s",
                 material_id, completion_date)


async def _end_of_reading() -> datetime.date:
    reading_stat = await reading_statistics()
    remaining_days = sum(
        stat.remaining_days or 0
        for stat in reading_stat
    )
    return datetime.date.today() + datetime.timedelta(days=remaining_days)


async def estimate() -> list[MaterialEstimate]:
    """ Get materials from queue with estimated time to read """
    step = datetime.timedelta(days=1)

    # start when all reading material will be completed
    start = await _end_of_reading()
    avg = await statistics.get_avg_read_pages()

    last_date = start + step
    forecasts = []

    for material in await get_free_materials():
        expected_duration = round(material.pages / avg)
        expected_end = last_date + datetime.timedelta(days=expected_duration)

        forecast = MaterialEstimate(
            material=material,
            will_be_started=last_date,
            will_be_completed=expected_end,
            expected_duration=expected_duration
        )
        forecasts += [forecast]

        last_date = expected_end + step

    return forecasts
