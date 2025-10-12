import datetime
import random
import uuid
from decimal import Decimal
from typing import Literal

import pytest
import sqlalchemy.sql as sa

from tracker.common import database
from tracker.materials import db
from tracker.models import models
from tracker.reading_log import statistics


async def get_materials() -> list[db.Material]:
    stmt = sa.select(models.Materials)

    async with database.session() as ses:
        return [db.Material(**row) for row in (await ses.execute(stmt)).mappings().all()]


async def get_statuses() -> list[db.Status]:
    stmt = sa.select(models.Statuses)

    async with database.session() as ses:
        return [db.Status(**row) for row in (await ses.execute(stmt)).mappings().all()]


async def test_get_means():
    from tracker.reading_log.statistics import get_means

    assert await db.get_means() == await get_means()


@pytest.mark.parametrize("material_id", [None, "fd569d08-240e-4f60-b39d-e37265fbfe24"])
async def test_get_material(material_id):
    if not material_id:
        assert await db.get_material(material_id=str(uuid.uuid4())) is None
        return

    material = await db.get_material(material_id=material_id)

    stmt = sa.select(models.Materials).where(
        models.Materials.c.material_id == material_id,
    )

    async with database.session() as ses:
        row = (await ses.execute(stmt)).mappings().one()
    expected = db.Material(**row)

    assert expected == material


async def test_get_free_materials():
    free_materials = await db._get_free_materials()

    materials = await get_materials()
    statuses = await get_statuses()
    status_ids = {status.material_id for status in statuses}

    expected_free_materials = {
        material.material_id
        for material in materials
        if material.material_id not in status_ids
    }

    assert len(free_materials) == len(expected_free_materials)
    assert all(
        material.material_id in expected_free_materials for material in free_materials
    )


def test_get_reading_materials_stmt():
    stmt = db._get_reading_materials_stmt()

    assert isinstance(stmt, sa.Select)


def test_get_completed_materials_stmt():
    stmt = db._get_completed_materials_stmt()

    assert isinstance(stmt, sa.Select)


@pytest.mark.parametrize("is_completed", [True, False])
async def test_parse_material_status_response(is_completed):
    if is_completed:
        stmt = db._get_completed_materials_stmt()
    else:
        stmt = db._get_reading_materials_stmt()

    result = await db._parse_material_status_response(stmt=stmt)
    assert result


async def test_get_reading_materials():
    reading_materials = await db.get_reading_materials()

    materials = {material.material_id: material for material in await get_materials()}
    statuses = {status.material_id: status for status in await get_statuses()}

    expected = {
        material_id
        for material_id in materials
        if material_id in statuses and not statuses[material_id].completed_at
    }

    assert len(reading_materials) == len(expected)
    assert all(material.material_id in expected for material in reading_materials)

    assert all(
        material.material == materials[material.material_id]
        for material in reading_materials
    )
    assert all(
        material.status == statuses[material.material_id]
        for material in reading_materials
    )


async def test_get_completed_materials():
    completed_materials = await db._get_completed_materials()

    materials = {material.material_id: material for material in await get_materials()}
    statuses = {status.material_id: status for status in await get_statuses()}

    expected = {
        material_id
        for material_id in materials
        if material_id in statuses and statuses[material_id].completed_at
    }

    assert len(completed_materials) == len(expected)
    assert all(material.material_id in expected for material in completed_materials)

    assert all(
        material.material == materials[material.material_id]
        for material in completed_materials
    )
    assert all(
        material.status == statuses[material.material_id]
        for material in completed_materials
    )


async def test_get_last_material_started():
    material_id = await db.get_last_material_started()

    stmt = (
        sa.select(models.Materials.c.material_id)
        .join(
            models.Statuses,
            models.Statuses.c.material_id == models.Materials.c.material_id,
        )
        .join(
            models.ReadingLog,
            models.ReadingLog.c.material_id == models.Materials.c.material_id,
            isouter=True,
        )
        .where(models.Statuses.c.completed_at == None)
        .order_by(models.ReadingLog.c.date.desc())
        .order_by(models.Statuses.c.started_at.desc())
        .limit(1)
    )

    async with database.session() as ses:
        expected = await ses.scalar(stmt)

    assert expected == material_id


@pytest.mark.parametrize("material_status", ["completed", "started", "not started"])
async def test_get_status(
    material_status: Literal["completed", "started", "not started"],
):
    materials = {material.material_id: material for material in await get_materials()}
    statuses = {status.material_id: status for status in await get_statuses()}

    if material_status == "not started":
        material_id = random.choice(
            [material_id for material_id in materials if material_id not in statuses],
        )
    elif material_status == "completed":
        material_id = random.choice(
            [
                material_id
                for material_id in materials
                if material_id in statuses and statuses[material_id].completed_at
            ],
        )
    elif material_status == "started":
        material_id = random.choice(
            [
                material_id
                for material_id in materials
                if material_id in statuses and not statuses[material_id].completed_at
            ],
        )

    status = await db._get_status(material_id=material_id)
    assert status == statuses.get(material_id)


@pytest.mark.parametrize(
    ("duration", "expected"),
    [
        (365, "1 years"),
        (1, "1 days"),
        (30, "1 months"),
        (31, "1 months, 1 days"),
        (65, "2 months, 5 days"),
        (395, "1 years, 1 months"),
        (790, "2 years, 2 months"),
        (380, "1 years, 15 days"),
        (792, "2 years, 2 months, 2 days"),
        (datetime.timedelta(days=792), "2 years, 2 months, 2 days"),
    ],
)
def test_convert_duration_to_period(duration, expected):
    assert db._convert_duration_to_period(duration) == expected


@pytest.mark.parametrize(
    ("start", "finish", "expected"),
    [
        (database.utcnow(), database.utcnow(), "1 days"),
        (database.utcnow() - datetime.timedelta(days=6), database.utcnow(), "7 days"),
        (database.utcnow() - datetime.timedelta(days=6), None, "7 days"),
        (database.utcnow() - datetime.timedelta(days=30), None, "1 months, 1 days"),
        (
            database.utcnow() - datetime.timedelta(days=30),
            database.utcnow(),
            "1 months, 1 days",
        ),
    ],
)
def test_get_total_reading_duration(start, finish, expected):
    assert (
        db._get_total_reading_duration(started_at=start, completed_at=finish) == expected
    )


async def test_get_material_statistics():
    pass


async def test_get_material_statistics_unread():
    materials = await db._get_free_materials()
    assert materials

    material = random.choice(materials)
    material_status = db.MaterialStatus(
        material=material,
        status=db.Status(
            status_id=uuid.uuid4(),
            material_id=material.material_id,
            started_at=database.utcnow().date(),
        ),
    )
    mean_total = Decimal(50)
    m_log_st = await statistics.calculate_materials_stat(
        material_ids={material.material_id},
    )

    result = db._get_material_statistics(
        material_status=material_status,
        notes_count=10,
        mean_total=mean_total,
        log_stats={material.material_id: m_log_st},
    )

    assert result.completed_at is None
    assert result.total_reading_duration == "1 days"
    assert result.duration == 0
    assert result.total == 0
    assert result.lost_time == 0
    assert result.min_record is None
    assert result.max_record is None
    assert result.remaining_pages == material.pages
    assert result.remaining_days == round(material.pages / mean_total)
    assert result.would_be_completed == (
        datetime.date.today() + datetime.timedelta(days=result.remaining_days)
    )


async def test_completed_statistics():
    materials = list(await db._get_completed_materials())
    m_log_st = await statistics.calculate_materials_stat(
        material_ids={m.material_id for m in materials},
    )

    result = await db.completed_statistics()
    assert len(result) == len(materials)
    for st in result:
        assert st.remaining_pages is None
        assert st.remaining_days is None
        assert st.completed_at
        assert st.would_be_completed is None

        log_st = m_log_st[st.material.material_id]
        assert st.total_reading_duration
        assert st.duration == log_st.duration
        assert st.lost_time == log_st.lost_time
        assert st.mean == log_st.mean
        assert st.total == log_st.total
        assert st.min_record == log_st.min_record
        assert st.max_record == log_st.max_record


async def test_reading_statistics():
    log_exists = sa.func.exists(
        sa.select(1)
        .select_from(models.ReadingLog)
        .where(models.ReadingLog.c.material_id == models.Materials.c.material_id)
        .scalar_subquery(),
    )
    reading_materials_stmt = db._get_reading_materials_stmt().where(log_exists)

    materials = list(
        await db._parse_material_status_response(
            stmt=reading_materials_stmt,
        ),
    )
    m_log_st = await statistics.calculate_materials_stat(
        material_ids={m.material_id for m in materials},
    )

    result = await db.reading_statistics()
    assert len(result) >= len(materials)

    for st in result:
        if (m_id := st.material.material_id) not in m_log_st:
            print(f"ERROR: unread material skipped {m_id}")  # noqa: T201
            continue
        log_st = m_log_st[m_id]

        assert st.remaining_pages == st.material.pages - log_st.total
        assert st.remaining_days == round((st.material.pages - st.total) / st.mean)
        assert st.completed_at is None
        assert st.would_be_completed is not None

        assert st.total_reading_duration
        assert st.duration == log_st.duration
        assert st.lost_time == log_st.lost_time
        assert st.mean == log_st.mean
        assert st.total == log_st.total
        assert st.min_record == log_st.min_record
        assert st.max_record == log_st.max_record


async def test_get_material_tags():
    tags = await db.get_material_tags()
    materials = await get_materials()

    for tag in tags:
        assert tag.islower(), repr(tag)
        assert not (tag.startswith(" ") or tag.endswith(" ")), repr(tag)

    stmt = sa.select(models.Materials.c.tags).where(models.Materials.c.tags != None)

    async with database.session() as ses:
        tags_db = await ses.scalars(stmt)

    expected = set()
    for tag in tags_db:
        expected |= {tag.strip().lower() for tag in tag.split(",")}

    assert expected == tags

    assert all(
        all(tag.strip().lower() in tags for tag in material.tags.split(","))
        for material in materials
        if material.tags
    )


async def test_insert_material():
    pass


async def test_update_material():
    pass


async def test_start_material():
    pass


async def test_start_material_invalid_date():
    material_id = uuid.UUID("44582686-ff27-4e4b-8d32-8bfdccc085b7")
    date = (database.utcnow() + datetime.timedelta(days=1)).date()

    with pytest.raises(ValueError) as e:
        await db.start_material(material_id=material_id, started_at=date)

    assert str(e.value) == "Start date must be less than today"


async def test_complete_material():
    pass


@pytest.mark.parametrize(
    ("material_status", "exc"),
    [
        ("completed", "Material is already completed"),
        ("not started", "Material is not started"),
    ],
)
async def test_complete_material_invalid_materials(
    material_status: Literal["completed", "not started"],
    exc,
):
    materials = {material.material_id: material for material in await get_materials()}
    statuses = {status.material_id: status for status in await get_statuses()}

    if material_status == "not started":
        material_id = random.choice(
            [material_id for material_id in materials if material_id not in statuses],
        )
    elif material_status == "completed":
        material_id = random.choice(
            [
                material_id
                for material_id in materials
                if material_id in statuses and statuses[material_id].completed_at
            ],
        )

    with pytest.raises(ValueError) as e:
        await db.complete_material(material_id=material_id)

    assert exc == str(e.value)


async def test_complete_material_invalid_date():
    materials = {material.material_id: material for material in await get_materials()}
    statuses = {status.material_id: status for status in await get_statuses()}

    material_id = random.choice(
        [
            material_id
            for material_id in materials
            if material_id in statuses and not statuses[material_id].completed_at
        ],
    )

    date = (statuses[material_id].started_at - datetime.timedelta(days=1)).date()

    with pytest.raises(ValueError) as e:
        await db.complete_material(material_id=material_id, completed_at=date)

    assert str(e.value) == "Completion date must be greater than start date"


async def test_outline_material():
    pass


async def test_repeat_material():
    pass


async def test_end_of_reading():
    pass


async def test_estimate():
    pass


@pytest.mark.parametrize(
    ("priority_days", "repeats_count", "expected"),
    [
        (None, 0, 0),
        (29, 0, 0),
        (30, 0, 1),
        # 44 / 30 < 1.5 rounds to 1
        (44, 0, 1),
        # but when 45 / 30 = 1.5 rounds to 2
        (45, 0, 1),
        (59, 0, 1),
        (92, 0, 3),
        (2, 0, 0),
        (0, 0, 0),
        (2, 2, 0),
        (0, 3, 0),
        (180, 3, 3),
        (30, 1, 0),
        (80, 2, 0),
        (102, 2, 1),
    ],
)
def test_calculate_priority_months(priority_days, repeats_count, expected):
    assert (
        int(db._calculate_priority_months(priority_days, repeats_count=repeats_count))
        == expected
    ), priority_days


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        (None, 0),
        (datetime.timedelta(days=29), 29),
        (datetime.timedelta(days=0), 0),
        (datetime.timedelta(days=92), 92),
    ],
)
def test_get_priority_days(field, expected):
    assert db._get_priority_days(field) == expected


async def test_get_repeats_analytics_only_repeated():
    stmt = sa.select(
        models.Repeats.c.material_id,
        sa.func.max(models.Repeats.c.repeated_at).label("last_repeated_at"),
        sa.func.count(1).label("repeats_count"),
    ).group_by(models.Repeats.c.material_id)

    async with database.session() as ses:
        repeats = {row.material_id: row for row in await ses.execute(stmt)}

    result = {
        material_id: r
        for material_id, r in (await db.get_repeats_analytics()).items()
        if r.last_repeated_at
    }
    assert len(result) == len(repeats) != 0

    for material_id, repeat in result.items():
        valid_repeat = repeats[material_id]
        assert repeat.repeats_count == valid_repeat.repeats_count
        assert repeat.last_repeated_at == valid_repeat.last_repeated_at

        assert repeat.priority_days == (
                database.utcnow().date() - valid_repeat.last_repeated_at.date()).days


async def test_get_repeats_analytics_only_not_repeated():
    pass


@pytest.mark.parametrize(
    ("material_id", "expected"),
    [
        ("5a07cc0c-21e4-4228-b3ff-7c8bc9019ec4", True),
        # even completed
        ("b06298ed-6f22-4c36-99eb-8a0d329e002d", False),
        # not started
        ("7e4209c9-60a4-4478-bfd2-47b1956ed496", False),
        # not exists
        ("ec1e1ead-da6e-4b03-9425-4b8953c85cb4", False),
    ],
)
async def test_is_reading(material_id, expected):
    result = await db.is_reading(material_id=uuid.UUID(material_id))

    assert result is expected, material_id
