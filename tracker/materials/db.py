import asyncio
import datetime
from typing import NamedTuple
from uuid import UUID

import sqlalchemy.sql as sa

from tracker.common import database, models
from tracker.common.log import logger
from tracker.notes import db as notes_db
from tracker.reading_log import statistics


class Material(NamedTuple):
    material_id: UUID
    title: str
    authors: str
    pages: int
    tags: str | None
    added_at: datetime.datetime
    is_outlined: bool


class Status(NamedTuple):
    status_id: UUID
    material_id: UUID
    started_at: datetime.datetime
    completed_at: datetime.datetime | None


class MaterialStatus(NamedTuple):
    material: Material
    status: Status


class MaterialEstimate(NamedTuple):
    material: Material
    will_be_started: datetime.date
    will_be_completed: datetime.date
    expected_duration: int


class MaterialStatistics(NamedTuple):
    material: Material
    started_at: datetime.date
    duration: int
    lost_time: int
    total: int
    min_record: database.MinMax | None
    max_record: database.MinMax | None
    average: int
    notes_count: int
    remaining_pages: int | None = None
    remaining_days: int | None = None
    completed_at: datetime.date | None = None
    total_reading_duration: str | None = None
    # date when the material would be completed
    # according to average read pages count
    would_be_completed: datetime.date | None = None


class RepeatAnalytics(NamedTuple):
    repeats_count: int
    last_repeated_at: datetime.datetime
    # how many days ago the material was last repeated,
    #  the clean priority
    last_repeat: int
    # priority to show in web, clean priority - 29
    priority: int


class RepeatingQueue(NamedTuple):
    material_id: UUID
    title: str
    pages: int
    notes_count: int
    repeats_count: int
    completed_at: datetime.date
    last_repeated_at: datetime.date
    # how many days ago the material was last repeated
    last_repeat: int


async def get_material(*,
                       material_id: UUID) -> Material | None:
    stmt = sa.select(models.Materials)\
        .where(models.Materials.c.material_id == str(material_id))

    async with database.session() as ses:
        if material := (await ses.execute(stmt)).mappings().one_or_none():
            return Material(**material)
    return None


async def _get_free_materials() -> list[Material]:
    logger.debug("Getting free materials")

    assigned_condition = sa.select(1) \
        .select_from(models.Statuses) \
        .where(models.Statuses.c.material_id == models.Materials.c.material_id)

    stmt = sa.select(models.Materials) \
        .where(~sa.exists(assigned_condition)) \
        .order_by(models.Materials.c.added_at)

    async with database.session() as ses:
        return [
            Material(**row)
            for row in (await ses.execute(stmt)).mappings().all()
        ]


def _get_reading_materials_stmt() -> sa.Select:
    return sa.select([models.Materials,
                      models.Statuses]) \
        .join(models.Statuses,
              models.Materials.c.material_id == models.Statuses.c.material_id) \
        .where(models.Statuses.c.completed_at == None) \
        .order_by(models.Statuses.c.started_at)


def _get_completed_materials_stmt() -> sa.Select:
    return sa.select([models.Materials,
                      models.Statuses]) \
        .join(models.Statuses,
              models.Materials.c.material_id == models.Statuses.c.material_id) \
        .where(models.Statuses.c.completed_at != None) \
        .order_by(models.Statuses.c.completed_at)


async def _parse_material_status_response(*,
                                          stmt: sa.Select) -> list[MaterialStatus]:
    async with database.session() as ses:
        return [
            MaterialStatus(
                material=Material(
                    material_id=row.material_id,
                    title=row.title,
                    authors=row.authors,
                    pages=row.pages,
                    tags=row.tags,
                    added_at=row.added_at,
                    is_outlined=row.is_outlined
                ),
                status=Status(
                    status_id=row.status_id,
                    material_id=row.material_id,
                    started_at=row.started_at,
                    completed_at=row.completed_at
                )
            )
            for row in (await ses.execute(stmt)).mappings().all()
        ]


async def _get_reading_materials() -> list[MaterialStatus]:
    logger.info("Getting reading materials")

    reading_materials_stmt = _get_reading_materials_stmt()
    reading_materials = await _parse_material_status_response(
        stmt=reading_materials_stmt)

    logger.info("%s reading materials found", len(reading_materials))

    return reading_materials


async def _get_completed_materials() -> list[MaterialStatus]:
    logger.info("Getting completed materials")

    completed_materials_stmt = _get_completed_materials_stmt()
    completed_materials = await _parse_material_status_response(
        stmt=completed_materials_stmt)

    logger.info("% completed materials found", len(completed_materials))

    return completed_materials


async def get_last_material_started() -> UUID | None:
    logger.info("Getting the last material started")

    stmt = _get_reading_materials_stmt()
    stmt = stmt.order_by(models.Statuses.c.started_at.desc())\
        .limit(1)

    async with database.session() as ses:
        if material := (await ses.execute(stmt)).mappings().first():
            logger.debug("The last material started='%s'", material.material_id)
            return material.material_id

    logger.debug("The last material started not found")
    return None


async def _get_status(*,
                      material_id: UUID) -> Status | None:
    logger.debug("Getting status for material_id=%s", material_id)

    stmt = sa.select(models.Statuses) \
        .where(models.Statuses.c.material_id == str(material_id))

    async with database.session() as ses:
        return (await ses.execute(stmt)).mappings().one_or_none()


def _convert_duration_to_period(duration: datetime.timedelta) -> str:
    total_days = duration.days
    years_str = months_str = days_str = ''

    if years := total_days // 365:
        years_str = f"{years} years "
    if months := total_days % 365 // 30:
        months_str = f"{months} months "
    if days := total_days % 30:
        days_str = f"{days} days"

    return f"{years_str}{months_str}{days_str}".strip()


def _get_total_reading_duration(*,
                                started_at: datetime.datetime,
                                completed_at: datetime.datetime | None) -> str:
    completion_date = completed_at or datetime.datetime.utcnow().date()
    duration = completion_date - started_at + datetime.timedelta(days=1)

    return _convert_duration_to_period(duration)


async def _get_material_statistics(*,
                                   material_status: MaterialStatus,
                                   notes_count: int = None,
                                   avg_total: int = None) -> MaterialStatistics:
    """ Calculate statistics for reading or completed material """
    material, status = material_status
    material_id = material.material_id

    logger.debug("Calculating statistics for material_id=%s", material_id)

    notes_count_: int = notes_count or await notes_db.get_notes_count(material_id=material_id)
    avg_total_: int = avg_total or await statistics.get_avg_read_pages()

    if was_reading := await statistics.contains(material_id=material_id):
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
        if not was_reading:
            remaining_days = round(remaining_pages / avg_total_)

        would_be_completed = database.today() + datetime.timedelta(days=remaining_days)
    else:
        would_be_completed = remaining_days = remaining_pages = None # type: ignore

    total_reading_duration = _get_total_reading_duration(
        started_at=status.started_at, completed_at=status.completed_at)

    return MaterialStatistics(
        material=material,
        started_at=status.started_at,
        completed_at=status.completed_at,
        total_reading_duration=total_reading_duration,
        duration=duration,
        lost_time=lost_time,
        total=total,
        min_record=min_record,
        max_record=max_record,
        average=avg,
        notes_count=notes_count_,
        remaining_pages=remaining_pages,
        remaining_days=remaining_days,
        would_be_completed=would_be_completed,
    )


async def completed_statistics() -> list[MaterialStatistics]:
    logger.info("Calculating completed materials statistics")

    completed_materials_task = asyncio.create_task(_get_completed_materials())
    avg_read_pages_task = asyncio.create_task(statistics.get_avg_read_pages())
    all_notes_count_task = asyncio.create_task(notes_db.get_all_notes_count())

    await asyncio.gather(
        completed_materials_task,
        avg_read_pages_task,
        all_notes_count_task
    )

    all_notes_count = all_notes_count_task.result()
    avg_read_pages = avg_read_pages_task.result()
    completed_materials = completed_materials_task.result()

    return [
        await _get_material_statistics(
            material_status=material_status,
            notes_count=all_notes_count.get(material_status.material.material_id, 0),
            avg_total=avg_read_pages
        )
        for material_status in completed_materials
    ]


async def reading_statistics() -> list[MaterialStatistics]:
    logger.info("Calculating reading materials statistics")

    reading_materials_task = asyncio.create_task(_get_reading_materials())
    avg_read_pages_task = asyncio.create_task(statistics.get_avg_read_pages())
    all_notes_count_task = asyncio.create_task(notes_db.get_all_notes_count())

    await asyncio.gather(
        reading_materials_task,
        all_notes_count_task,
        avg_read_pages_task
    )

    all_notes_count = all_notes_count_task.result()
    avg_read_pages = avg_read_pages_task.result()
    reading_materials = reading_materials_task.result()

    return [
        await _get_material_statistics(
            material_status=material_status,
            notes_count=all_notes_count.get(material_status.material.material_id, 0),
            avg_total=avg_read_pages
        )
        for material_status in reading_materials
    ]


async def add_material(*,
                       title: str,
                       authors: str,
                       pages: int,
                       tags: str | None) -> None:
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
                         start_date: datetime.date | None = None) -> None:
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
                            completion_date: datetime.date | None = None) -> None:
    logger.debug("Completing material_id=%s", material_id)
    completion_date = completion_date or database.today().date()

    if (status := await _get_status(material_id=material_id)) is None:
        raise ValueError("Material is not started")
    if status.completed_at is not None:
        raise ValueError("Material is already completed")
    if status.started_at > completion_date:
        raise ValueError("Completion date must be greater than start date")

    values = {
        "completed_at": completion_date
    }
    stmt = models.Statuses\
        .update().values(values)\
        .where(models.Statuses.c.material_id == str(material_id))

    async with database.session() as ses:
        await ses.execute(stmt)

    logger.debug("Material_id=%s completed at %s",
                 material_id, completion_date)


async def outline_material(*,
                           material_id: UUID) -> None:
    logger.info("Outlining material='%s'", material_id)

    values = {
        "is_outlined": True
    }

    stmt = models.Materials\
        .update().values(values)\
        .where(models.Materials.c.material_id == str(material_id))

    async with database.session() as ses:
        await ses.execute(stmt)

    logger.info("Material='%s' outlined", material_id)


async def _end_of_reading() -> datetime.date:
    remaining_days = sum(
        stat.remaining_days or 0
        for stat in await reading_statistics()
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

    for material in await _get_free_materials():
        expected_duration = round(material.pages / avg)
        expected_end = last_date + datetime.timedelta(days=expected_duration)

        forecasts += [MaterialEstimate(
            material=material,
            will_be_started=last_date,
            will_be_completed=expected_end,
            expected_duration=expected_duration
        )]

        last_date = expected_end + step

    return forecasts


async def get_repeats_analytics() -> dict[UUID, RepeatAnalytics]:
    last_repeated_at = sa.func.max(models.Repeats.c.repeated_at).label("last_repeated_at")
    repetition_or_completion_date = sa.func.coalesce(last_repeated_at, sa.func.max(models.Statuses.c.completed_at))
    stmt = sa.select([models.Repeats.c.material_id,
                      sa.func.count(1).label("count"),
                      last_repeated_at,
                      (sa.func.now() - repetition_or_completion_date).label('last_repeat')])\
        .join(models.Statuses,
              models.Statuses.c.material_id == models.Repeats.c.material_id)\
        .group_by(models.Repeats.c.material_id)

    async with database.session() as ses:
        return {
            row.material_id: RepeatAnalytics(
                repeats_count=row.count,
                last_repeated_at=row.last_repeated_at,
                last_repeat=row.last_repeat,
                priority=row.last_repeat - 29
            )
            for row in await ses.execute(stmt)
        }


async def get_repeating_queue() -> list[RepeatingQueue]:
    pass
