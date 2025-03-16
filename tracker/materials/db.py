import asyncio
import datetime
import time
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

import aiohttp
import bs4
import sqlalchemy.sql as sa
from pydantic import ConfigDict, computed_field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.cards import db as cards_db
from tracker.common import database, settings
from tracker.common.logger import logger
from tracker.common.schemas import CustomBaseModel
from tracker.models import enums, models
from tracker.notes import db as notes_db


class Material(CustomBaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    material_id: UUID
    index: int
    title: str
    authors: str
    pages: int
    material_type: enums.MaterialTypesEnum
    tags: str | None
    link: str | None
    added_at: datetime.datetime
    is_outlined: bool


class Status(CustomBaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    status_id: UUID
    material_id: UUID
    started_at: datetime.datetime
    completed_at: datetime.datetime | None = None


class MaterialStatus(CustomBaseModel):
    material: Material
    status: Status

    @property
    def material_id(self) -> UUID:
        return self.material.material_id


class MaterialEstimate(CustomBaseModel):
    material: Material
    will_be_started: datetime.date
    will_be_completed: datetime.date
    expected_duration: int


class MaterialStatistics(CustomBaseModel):
    material: Material
    started_at: datetime.date
    duration: int
    lost_time: int
    total: int
    min_record: database.MinMax | None
    max_record: database.MinMax | None
    mean: int
    notes_count: int
    remaining_pages: int | None = None
    remaining_days: int | None = None
    completed_at: datetime.date | None = None
    total_reading_duration: str | None = None
    # date when the material would be completed
    # according to mean read pages count
    would_be_completed: datetime.date | None = None

    @property
    def percent_completed(self) -> float:
        return round(self.total / self.material.pages * 100, 2)


class RepeatAnalytics(CustomBaseModel):
    repeats_count: int
    last_repeated_at: datetime.datetime | None
    # total days since last seen
    priority_days: int

    @field_validator("priority_days", mode="before")
    def replace_none(cls, v: int | None) -> int:
        return v or 0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def priority_months(self) -> float:
        return _calculate_priority_months(
            self.priority_days,
            repeats_count=self.repeats_count,
        )


class RepeatingQueue(CustomBaseModel):
    material_id: UUID
    title: str
    pages: int
    material_type: enums.MaterialTypesEnum
    is_outlined: bool
    notes_count: int
    cards_count: int
    repeats_count: int
    completed_at: datetime.datetime | None
    last_repeated_at: datetime.datetime | None
    priority_days: int
    priority_months: float


async def get_means() -> enums.MEANS:
    from tracker.reading_log.statistics import get_means

    return await get_means()


async def get_material(*, material_id: UUID) -> Material | None:
    logger.debug("Getting material=%s", material_id)
    stmt = sa.select(models.Materials).where(
        models.Materials.c.material_id == material_id,
    )

    async with database.session() as ses:
        if material := (await ses.execute(stmt)).one_or_none():
            logger.debug("Material got")
            return Material.model_validate(material, from_attributes=True)

    logger.warning("Material id=%s not found", material_id)
    return None


async def get_materials() -> list[Material]:
    stmt = sa.select(models.Materials)

    async with database.session() as ses:
        return [
            Material.model_validate(material, from_attributes=True)
            for material in (await ses.execute(stmt)).all()
        ]


async def _get_free_materials() -> list[Material]:
    logger.debug("Getting free materials")

    assigned_condition = (
        sa.select(1)
        .select_from(models.Statuses)
        .where(models.Statuses.c.material_id == models.Materials.c.material_id)
    )

    stmt = (
        sa.select(models.Materials)
        .where(~sa.exists(assigned_condition))
        .order_by(models.Materials.c.index)
    )

    async with database.session() as ses:
        materials = [
            Material.model_validate(row, from_attributes=True)
            for row in (await ses.execute(stmt)).all()
        ]

    logger.debug("%s free materials got", len(materials))
    return materials


def _get_reading_materials_stmt() -> sa.Select:
    reading_logs_cte = (
        sa.select(
            models.ReadingLog.c.material_id,
            sa.func.max(models.ReadingLog.c.date).label("date"),
        )
        .group_by(models.ReadingLog.c.material_id)
        .cte("reading_logs")
    )

    return (
        sa.select(models.Materials, models.Statuses)
        .join(models.Statuses)
        .join(reading_logs_cte, isouter=True)
        .where(models.Statuses.c.completed_at == None)
        .order_by(reading_logs_cte.c.date.desc())
    )


def _get_completed_materials_stmt() -> sa.Select:
    return (
        sa.select(models.Materials, models.Statuses)
        .join(models.Statuses)
        .where(models.Statuses.c.completed_at != None)
        .order_by(models.Statuses.c.completed_at)
    )


async def _parse_material_status_response(*, stmt: sa.Select) -> list[MaterialStatus]:
    async with database.session() as ses:
        return [
            MaterialStatus(
                material=Material.model_validate(row, from_attributes=True),
                status=Status.model_validate(row, from_attributes=True),
            )
            for row in (await ses.execute(stmt)).mappings().all()
        ]


async def get_reading_materials() -> list[MaterialStatus]:
    logger.info("Getting reading materials")

    reading_materials_stmt = _get_reading_materials_stmt()
    reading_materials = await _parse_material_status_response(stmt=reading_materials_stmt)

    logger.info("%s reading materials found", len(reading_materials))
    return reading_materials


async def _get_completed_materials() -> list[MaterialStatus]:
    logger.info("Getting completed materials")

    completed_materials_stmt = _get_completed_materials_stmt()
    completed_materials = await _parse_material_status_response(
        stmt=completed_materials_stmt,
    )

    logger.info("%s completed materials found", len(completed_materials))
    return completed_materials


async def get_last_material_started() -> UUID | None:
    """Get last started and not completed material."""
    logger.info("Getting the last material started")

    stmt = (
        _get_reading_materials_stmt()
        .order_by(models.Statuses.c.started_at.desc())
        .limit(1)
    )

    async with database.session() as ses:
        if material := (await ses.execute(stmt)).first():
            logger.debug("The last material started='%s'", material.material_id)
            return material.material_id

    logger.debug("The last material started not found")
    return None


async def _get_status(*, material_id: UUID) -> Status | None:
    logger.debug("Getting status for material_id=%s", material_id)

    stmt = sa.select(models.Statuses).where(models.Statuses.c.material_id == material_id)

    async with database.session() as ses:
        if status := (await ses.execute(stmt)).one_or_none():
            logger.debug("Status got")
            return Status.model_validate(status, from_attributes=True)

    logger.debug("Status not found")
    return None


def _convert_duration_to_period(duration: datetime.timedelta | int) -> str:
    if isinstance(duration, datetime.timedelta):
        total_days = duration.days
    else:
        total_days = duration

    period = []
    if years := total_days // 365:
        period.append(f"{years} years")
    if months := total_days % 365 // 30:
        period.append(f"{months} months")
    if days := total_days % 365 % 30:
        period.append(f"{days} days")

    return ", ".join(period)


def _get_total_reading_duration(
    *,
    started_at: datetime.datetime,
    completed_at: datetime.datetime | None,
) -> str:
    completion_date = completed_at or database.utcnow()
    duration = completion_date - started_at + datetime.timedelta(days=1)

    return _convert_duration_to_period(duration)


def _get_material_statistics(
    *,
    material_status: MaterialStatus,
    notes_count: int,
    mean_total: Decimal,
    log_stats: dict[UUID, Any],
) -> MaterialStatistics:
    """Calculate statistics for reading or completed material."""
    material, status = material_status.material, material_status.status
    material_id = material.material_id

    if log_st := log_stats.get(material_id):
        mean, total = log_st.mean, log_st.total
        duration, lost_time = log_st.duration, log_st.lost_time

        max_record, min_record = log_st.max_record, log_st.min_record
    else:
        mean = round(mean_total)
        total = duration = lost_time = 0
        max_record = min_record = None

    if status.completed_at is None:
        remaining_pages = material.pages - total
        remaining_days = round(remaining_pages / mean)
        would_be_completed: datetime.date | None = (
            database.utcnow().date()
            + datetime.timedelta(
                days=remaining_days,
            )
        )
    else:
        would_be_completed = remaining_days = remaining_pages = None

    total_reading_duration = _get_total_reading_duration(
        started_at=status.started_at,
        completed_at=status.completed_at,
    )

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
        mean=mean,
        notes_count=notes_count,
        remaining_pages=remaining_pages,
        remaining_days=remaining_days,
        would_be_completed=would_be_completed,
    )


async def completed_statistics() -> list[MaterialStatistics]:
    from tracker.reading_log.statistics import calculate_materials_stat

    logger.info("Calculating completed materials statistics")
    start = time.perf_counter()

    async with asyncio.TaskGroup() as tg:
        completed_materials_task = tg.create_task(_get_completed_materials())
        mean_read_pages_task = tg.create_task(get_means())
        all_notes_count_task = tg.create_task(notes_db.get_all_notes_count())

    material_statuses = completed_materials_task.result()
    ids = {ms.material_id for ms in material_statuses}
    log_stats = await calculate_materials_stat(ids)

    all_notes_count = all_notes_count_task.result()
    mean_read_pages = mean_read_pages_task.result()

    result = [
        _get_material_statistics(
            material_status=material_status,
            notes_count=all_notes_count.get(material_status.material_id, 0),
            mean_total=mean_read_pages.get(
                material_status.material.material_type,
                Decimal(1),
            ),
            log_stats=log_stats,
        )
        for material_status in material_statuses
    ]

    exec_time = round(time.perf_counter() - start, 2)
    logger.info("%s materials statistics calculated for %ss", len(result), exec_time)

    return result


async def reading_statistics() -> list[MaterialStatistics]:
    from tracker.reading_log.statistics import calculate_materials_stat

    logger.info("Calculating reading materials statistics")
    start = time.perf_counter()

    async with asyncio.TaskGroup() as tg:
        reading_materials_task = tg.create_task(get_reading_materials())
        mean_read_pages_task = tg.create_task(get_means())
        all_notes_count_task = tg.create_task(notes_db.get_all_notes_count())

    material_statuses = reading_materials_task.result()
    ids = {ms.material_id for ms in material_statuses}
    log_stats = await calculate_materials_stat(ids)
    all_notes_count = all_notes_count_task.result()
    mean_read_pages = mean_read_pages_task.result()

    result = [
        _get_material_statistics(
            material_status=material_status,
            notes_count=all_notes_count.get(material_status.material_id, 0),
            mean_total=mean_read_pages.get(
                material_status.material.material_type,
                Decimal(1),
            ),
            log_stats=log_stats,
        )
        for material_status in material_statuses
    ]

    exec_time = round(time.perf_counter() - start, 2)
    logger.info("%s materials statistics calculated for %ss", len(result), exec_time)

    return result


async def get_material_tags() -> set[str]:
    logger.info("Getting material tags")

    stmt = sa.select(models.Materials.c.tags).where(models.Materials.c.tags != None)

    async with database.session() as ses:
        tags_db = await ses.scalars(stmt)

    tags = set()
    for tag in tags_db:
        tags |= {tag.strip().lower() for tag in tag.split(",")}

    logger.debug("%s tags got", len(tags))
    return tags


async def insert_material(
    *,
    title: str,
    authors: str,
    pages: int,
    material_type: enums.MaterialTypesEnum,
    tags: str | None,
    link: str | None,
) -> None:
    logger.debug("Inserting material title=%s", title)

    values = {
        "title": title,
        "authors": authors,
        "pages": pages,
        "tags": tags,
        "link": link,
        "material_type": material_type,
    }
    stmt = models.Materials.insert().values(values)

    async with database.session() as ses:
        await ses.execute(stmt)

    logger.debug("Material inserted")


async def update_material(
    *,
    material_id: UUID,
    title: str,
    authors: str,
    pages: int,
    material_type: enums.MaterialTypesEnum,
    tags: str | None,
    link: str | None,
) -> None:
    logger.debug("Updating material='%s'", material_id)

    values = {
        "title": title,
        "authors": authors,
        "pages": pages,
        "material_type": material_type,
        "tags": tags,
        "link": link,
    }

    stmt = (
        models.Materials.update()
        .values(values)
        .where(models.Materials.c.material_id == material_id)
    )

    async with database.session() as ses:
        await ses.execute(stmt)

    logger.debug("Material updated")


async def start_material(
    *,
    material_id: UUID,
    start_date: datetime.date | None = None,
) -> None:
    start_date = start_date or database.utcnow().date()
    logger.debug("Starting material_id=%s", material_id)

    if start_date > database.utcnow().date():
        raise ValueError("Start date must be less than today")

    values = {"material_id": material_id, "started_at": start_date}
    stmt = models.Statuses.insert().values(values)

    async with database.session() as ses:
        await ses.execute(stmt)

    logger.debug("Material started")


async def complete_material(
    *,
    material_id: UUID,
    completion_date: datetime.date | None = None,
) -> None:
    logger.debug("Completing material_id=%s", material_id)
    completion_date = completion_date or database.utcnow().date()

    if (status := await _get_status(material_id=material_id)) is None:
        raise ValueError("Material is not started")
    if status.completed_at is not None:
        raise ValueError("Material is already completed")
    if status.started_at.date() > completion_date:
        raise ValueError("Completion date must be greater than start date")

    values = {"completed_at": completion_date}
    stmt = (
        models.Statuses.update()
        .values(values)
        .where(models.Statuses.c.material_id == material_id)
    )

    async with database.session() as ses:
        await ses.execute(stmt)

    logger.debug("Material completed at %s", completion_date)


async def outline_material(*, material_id: UUID) -> None:
    logger.info("Outlining material='%s'", material_id)

    values = {"is_outlined": True}

    stmt = (
        models.Materials.update()
        .values(values)
        .where(models.Materials.c.material_id == material_id)
    )

    async with database.session() as ses:
        await ses.execute(stmt)

    logger.info("Material outlined")


async def repeat_material(*, material_id: UUID) -> None:
    logger.debug("Repeating material_id='%s'", material_id)

    values = {"material_id": material_id, "repeated_at": database.utcnow()}
    stmt = models.Repeats.insert().values(values)

    async with database.session() as ses:
        await ses.execute(stmt)

    logger.debug("Material repeated")


async def _end_of_reading() -> datetime.date:
    remaining_days = sum(stat.remaining_days or 0 for stat in await reading_statistics())
    return database.utcnow().date() + datetime.timedelta(days=remaining_days)


async def estimate() -> list[MaterialEstimate]:
    """Get materials from queue with estimated time to read."""
    logger.info("Estimating materials started")
    step = datetime.timedelta(days=1)

    async with asyncio.TaskGroup() as tg:
        get_mean_task = tg.create_task(get_means())
        get_free_materials_task = tg.create_task(_get_free_materials())

    # start today, not when all reading material will be completed
    last_date = database.utcnow().date()
    mean = get_mean_task.result()
    forecasts = []

    for material in get_free_materials_task.result():
        mean_ = mean.get(material.material_type, 1)
        expected_duration = round(material.pages / mean_)
        expected_end = last_date + datetime.timedelta(days=expected_duration)
        # [start; stop]
        expected_duration += 1

        forecasts.append(
            MaterialEstimate(
                material=material,
                will_be_started=last_date,
                will_be_completed=expected_end,
                expected_duration=expected_duration,
            ),
        )

        last_date = expected_end + step

    logger.info("%s materials estimated", len(forecasts))
    return forecasts


def _calculate_priority_months(
    priority_days: int | None,
    *,
    repeats_count: int,
) -> float:
    if not priority_days:
        return 0

    priority_limit = repeats_count * 30
    if (days := priority_days) < priority_limit:
        return 0
    # priority should decrease having repeats count increased
    return (days - priority_limit) / 30


def _get_priority_days(priority_days: datetime.timedelta | None) -> int:
    return getattr(priority_days, "days", 0)


async def get_repeats_analytics() -> dict[UUID, RepeatAnalytics]:
    logger.debug("Getting repeat analytics")

    last_repeated_at = sa.func.max(models.Repeats.c.repeated_at).label("last_repeated_at")
    repet_or_compl_date = sa.func.coalesce(
        last_repeated_at,
        sa.func.max(models.Statuses.c.completed_at),
    )
    _dt = sa.func.date
    stmt = (
        sa.select(
            models.Statuses.c.material_id,
            sa.func.count(models.Repeats.c.repeat_id).label("repeats_count"),
            last_repeated_at,
            (_dt(sa.func.now()) - _dt(repet_or_compl_date)).label("priority_days"),
        )
        .join(
            models.Repeats,
            models.Repeats.c.material_id == models.Statuses.c.material_id,
            isouter=True,
        )
        .group_by(models.Statuses.c.material_id)
    )

    async with database.session() as ses:
        analytics = {
            row.material_id: RepeatAnalytics.model_validate(row, from_attributes=True)
            for row in (await ses.execute(stmt)).all()
        }

    logger.debug("%s materials to repeat got", len(analytics))
    return analytics


async def get_repeating_queue(*, is_outlined: bool) -> list[RepeatingQueue]:
    logger.debug("Getting repeating queue")

    async with asyncio.TaskGroup() as tg:
        completed_materials_task = tg.create_task(_get_completed_materials())
        notes_count_task = tg.create_task(notes_db.get_all_notes_count())
        cards_count_task = tg.create_task(cards_db.get_all_cards_count())
        repeat_analytics_task = tg.create_task(get_repeats_analytics())

    notes_count = notes_count_task.result()
    cards_count = cards_count_task.result()
    repeat_analytics = repeat_analytics_task.result()

    completed_materials = (
        material
        for material in completed_materials_task.result()
        # skip materials without notes and notwithstanding outlined
        if not (
            material.material.is_outlined and not notes_count.get(material.material_id)
        )
    )
    if is_outlined:
        completed_materials = (
            material for material in completed_materials if material.material.is_outlined
        )

    queue = [
        RepeatingQueue(
            material_id=material_status.material_id,
            title=material_status.material.title,
            pages=material_status.material.pages,
            material_type=material_status.material.material_type,
            is_outlined=material_status.material.is_outlined,
            completed_at=material_status.status.completed_at,
            notes_count=notes_count.get(material_status.material_id, 0),
            cards_count=cards_count.get(material_status.material_id, 0),
            repeats_count=repeat_analytics[material_status.material_id].repeats_count,
            last_repeated_at=repeat_analytics[
                material_status.material_id
            ].last_repeated_at,
            priority_days=repeat_analytics[material_status.material_id].priority_days,
            priority_months=repeat_analytics[material_status.material_id].priority_months,
        )
        for material_status in completed_materials
        if repeat_analytics[material_status.material_id].priority_months >= 1.0
    ]

    logger.debug("Repeating queue got, %s materials found", len(queue))
    return queue


async def get_queue_start() -> int:
    stmt = (
        sa.select(models.Materials.c.index)
        .join(models.Statuses, isouter=True)
        .where(models.Statuses.c.status_id == None)
        .order_by(models.Materials.c.index)
        .limit(1)
    )

    async with database.session() as ses:
        return await ses.scalar(stmt) or 1


async def get_queue_end() -> int:
    stmt = (
        sa.select(models.Materials.c.index)
        .join(models.Statuses, isouter=True)
        .where(models.Statuses.c.status_id == None)
        .order_by(models.Materials.c.index.desc())
        .limit(1)
    )

    async with database.session() as ses:
        return await ses.scalar(stmt) or 0


def _get_material_index_uniqueness_constraint_name() -> str:
    name: str | None = None

    # closure to cache
    def internal() -> str:
        nonlocal name
        if name:
            return name

        for constraint in models.Materials.constraints:
            if constraint.deferrable and constraint.contains_column(  # type: ignore[attr-defined]
                models.Materials.c.index,
            ):
                name = cast("str", constraint.name)
                return name

        raise ValueError("Deferrable material index constraint not found")

    return internal()


async def _set_unique_index_deferred(conn: AsyncSession) -> None:
    constraint_name = _get_material_index_uniqueness_constraint_name()
    await conn.execute(sa.text(f"SET CONSTRAINTS {constraint_name} DEFERRED"))


async def _set_unique_index_immediate(conn: AsyncSession) -> None:
    constraint_name = _get_material_index_uniqueness_constraint_name()
    await conn.execute(sa.text(f"SET CONSTRAINTS {constraint_name} IMMEDIATE"))


async def _shift_queue_down(*, conn: AsyncSession, start: int, stop: int) -> None:
    shift_queue_stmt = (
        models.Materials.update()
        .values({"index": models.Materials.c.index + 1})
        .where(models.Materials.c.index >= start)
        .where(models.Materials.c.index < stop)
    )

    await conn.execute(shift_queue_stmt)


async def _shift_queue_up(*, conn: AsyncSession, start: int, stop: int) -> None:
    shift_queue_stmt = (
        models.Materials.update()
        .values({"index": models.Materials.c.index - 1})
        .where(models.Materials.c.index > start)
        .where(models.Materials.c.index <= stop)
    )
    await conn.execute(shift_queue_stmt)


async def _get_material_index(material_id: UUID) -> int:
    if not (material := await get_material(material_id=material_id)):
        raise ValueError(f"Material id = {material_id} not found")

    return material.index


async def _set_material_index(
    *,
    material_id: UUID,
    index: int,
    conn: AsyncSession,
) -> None:
    logger.debug("Setting material_id=%s to index=%s", material_id, index)
    if not conn.in_transaction():
        raise ValueError("Could not update index outside a transaction")

    stmt = (
        models.Materials.update()
        .values({"index": index})
        .where(models.Materials.c.material_id == material_id)
    )

    await conn.execute(stmt)

    logger.debug("Index set")


async def swap_order(material_id: UUID, new_material_index: int) -> None:
    logger.info("Setting material=%s to %s index", material_id, new_material_index)

    async with database.transaction() as conn:
        old_material_index = await _get_material_index(material_id)
        logger.debug("Old material index = %s", old_material_index)

        if old_material_index == new_material_index:
            logger.warning("Indexes are equal, terminating")
            return

        await _set_unique_index_deferred(conn)
        # move to temporary index to save uniqueness
        await _set_material_index(material_id=material_id, index=-1, conn=conn)

        if old_material_index > new_material_index:
            logger.info("Move material upper")

            await _shift_queue_down(
                conn=conn,
                start=new_material_index,
                stop=old_material_index,
            )
        elif old_material_index < new_material_index:
            logger.info("Move material lower")

            await _shift_queue_up(
                conn=conn,
                start=old_material_index,
                stop=new_material_index,
            )
        else:
            raise ValueError(
                f"Wrong indexes got: {old_material_index}, "
                f"{new_material_index}, {material_id=}",
            )

        # set the target index
        await _set_material_index(
            material_id=material_id,
            index=new_material_index,
            conn=conn,
        )

        await _set_unique_index_immediate(conn)


async def is_reading(*, material_id: UUID) -> bool:
    stmt = (
        sa.select(sa.func.count(1) == 1)  # type: ignore[arg-type]
        .select_from(models.Statuses)
        .where(models.Statuses.c.material_id == material_id)
        .where(models.Statuses.c.completed_at == None)
    )

    async with database.session() as ses:
        return await ses.scalar(stmt) or False


async def get_html(link: str, *, http_timeout: int = 5) -> str:
    timeout = aiohttp.ClientTimeout(http_timeout)
    async with aiohttp.ClientSession(timeout=timeout) as ses:
        resp = await ses.get(str(link))
        resp.raise_for_status()

        return await resp.text("utf-8")


def _get_text(field: bs4.Tag | bs4.NavigableString | None) -> str:
    if isinstance(field, bs4.Tag):
        return field.get_text(strip=True)
    return ""


def parse_habr(html: str) -> dict[str, str]:
    soup = bs4.BeautifulSoup(html, "lxml")

    title = authors = None
    snippet = cast("bs4.Tag", soup.find("div", {"class": "tm-article-snippet"}))
    if snippet:
        title = snippet.find("h1", {"class": "tm-title"})
        authors = snippet.find("a", {"class": "tm-user-info__username"})

    return {"title": _get_text(title), "authors": _get_text(authors)}


def _parse_duration(duration: str) -> int:
    duration = (
        duration.replace("PT", "").replace("H", " ").replace("M", " ").replace("S", "")
    )

    parts = duration.split()
    total = 0

    if len(parts) == 3:  # noqa: PLR2004
        total += int(parts[0]) * 60
        parts.pop(0)
    if len(parts) == 2:  # noqa: PLR2004
        total += int(parts[0])
        parts.pop(0)
    if len(parts) == 1:
        total += round(int(parts[0]) / 60)

    return total


async def parse_youtube(video_id: str, *, http_timeout: int = 5) -> dict[str, str | int]:
    params = {
        "part": "snippet,contentDetails",
        "id": video_id,
        "key": settings.YOUTUBE_API_KEY,
    }

    timeout = aiohttp.ClientTimeout(http_timeout)
    async with aiohttp.ClientSession(timeout=timeout) as ses:
        resp = await ses.get(settings.YOUTUBE_API_URL, params=params)

        resp_json = await resp.json()
        resp.raise_for_status()

    item = resp_json["items"][0]
    title = item["snippet"]["title"]
    authors = item["snippet"]["channelTitle"]
    duration = item["contentDetails"]["duration"]

    return {"title": title, "authors": authors, "duration": _parse_duration(duration)}
