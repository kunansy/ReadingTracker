import base64
import datetime
import uuid
from decimal import Decimal

import pytest
from matplotlib.axes import Axes

from tests.integration import (
    factories,
    helpers_notes as helpers,
)
from tracker.common import database
from tracker.materials import db as materials_db
from tracker.models import enums, models
from tracker.notes import db as notes_db
from tracker.system import schemas, trends


SPAN_SIZE = 7
FIRST_DAY = helpers.day(-6)
LAST_DAY = helpers.day(0)
DAY_BEFORE = helpers.day(-7)
DAY_AFTER = helpers.day(1)
SPAN = trends.TimeSpan(start=FIRST_DAY, stop=LAST_DAY, span_size=SPAN_SIZE)
ONE_DAY_SPAN = trends.TimeSpan(start=LAST_DAY, stop=LAST_DAY, span_size=1)


@pytest.fixture(autouse=True)
def frozen_clock(mocker) -> None:
    mocker.patch.object(database, "utcnow", return_value=helpers.FROZEN_NOW)


def _days(
    amounts: dict[datetime.date, int],
    *,
    size: int = SPAN_SIZE,
) -> list[trends.DayStatistics]:
    return [
        trends.DayStatistics(
            date=helpers.day(offset),
            amount=amounts.get(helpers.day(offset), 0),
        )
        for offset in range(1 - size, 1)
    ]


async def _log(material_id: uuid.UUID, date: datetime.date, count: int) -> None:
    await factories.insert_log(material_id=material_id, count=count, date=date)


async def _note(material_id: uuid.UUID, added_at: datetime.datetime) -> uuid.UUID:
    return await helpers.insert_raw_note(material_id=material_id, added_at=added_at)


async def _completed(
    completed_at: datetime.datetime,
    material_type: enums.MaterialTypesEnum = enums.MaterialTypesEnum.book,
) -> uuid.UUID:
    material_id = await factories.insert_material(material_type=material_type)
    await factories.set_columns(
        models.Materials,
        material_id,
        started_at=helpers.at(helpers.day(-30)),
        completed_at=completed_at,
    )
    return material_id


async def _seed_reading_log() -> tuple[uuid.UUID, uuid.UUID]:
    book = await factories.start_material(material_type=enums.MaterialTypesEnum.book)
    article = await factories.start_material(
        material_type=enums.MaterialTypesEnum.article,
    )
    await _log(book, DAY_BEFORE, 1000)
    await _log(book, FIRST_DAY, 10)
    await _log(book, helpers.day(-3), 20)
    await _log(article, helpers.day(-3), 5)
    await _log(article, LAST_DAY, 7)
    await _log(book, DAY_AFTER, 2000)
    return book, article


READING_IN_SPAN = {FIRST_DAY: 10, helpers.day(-3): 25, LAST_DAY: 7}


async def test_reading_statistics_sum_the_log_per_day_inside_the_inclusive_span():
    await _seed_reading_log()

    stat = await trends._calculate_span_reading_statistics(SPAN)

    assert stat == READING_IN_SPAN


async def test_reading_statistics_of_a_one_day_span():
    await _seed_reading_log()

    assert await trends._calculate_span_reading_statistics(ONE_DAY_SPAN) == {LAST_DAY: 7}


async def _seed_notes() -> None:
    material_id = await factories.insert_material()
    await _note(material_id, helpers.at(DAY_BEFORE, 23, 59, 59))
    await _note(material_id, helpers.at(FIRST_DAY, 0, 0, 0))
    await _note(material_id, helpers.at(helpers.day(-2), 9))
    await _note(material_id, helpers.at(helpers.day(-2), 18))
    await _note(material_id, helpers.at(LAST_DAY, 23, 59, 59))
    await _note(material_id, helpers.at(DAY_AFTER, 0, 0, 0))
    deleted = await _note(material_id, helpers.at(helpers.day(-2), 12))
    await notes_db.delete_note(note_id=deleted)


NOTES_IN_SPAN = {FIRST_DAY: 1, helpers.day(-2): 2, LAST_DAY: 1}


async def test_notes_statistics_count_live_notes_per_day_inside_the_inclusive_span():
    await _seed_notes()

    assert await trends._calculate_span_notes_statistics(SPAN) == NOTES_IN_SPAN


async def _seed_completed_materials() -> None:
    await _completed(helpers.at(DAY_BEFORE, 23, 59, 59))
    await _completed(helpers.at(FIRST_DAY))
    await _completed(helpers.at(helpers.day(-1), 8), enums.MaterialTypesEnum.article)
    await _completed(helpers.at(helpers.day(-1), 20), enums.MaterialTypesEnum.article)
    await _completed(helpers.at(LAST_DAY, 23, 59, 59), enums.MaterialTypesEnum.course)
    await _completed(helpers.at(DAY_AFTER))
    await factories.start_material()
    await factories.insert_material()


COMPLETED_IN_SPAN = {FIRST_DAY: 1, helpers.day(-1): 2, LAST_DAY: 1}


async def test_completed_materials_statistics_count_completions_per_day_inside_the_span():
    await _seed_completed_materials()

    stat = await trends._calculate_span_completed_materials_statistics(SPAN)

    assert stat == COMPLETED_IN_SPAN


async def _seed_repeats() -> tuple[uuid.UUID, uuid.UUID]:
    first, second = uuid.uuid4(), uuid.uuid4()
    await helpers.insert_repeat(
        material_id=first,
        repeated_at=helpers.at(DAY_BEFORE, 23, 59, 59),
    )
    await helpers.insert_repeat(material_id=first, repeated_at=helpers.at(FIRST_DAY))
    await helpers.insert_repeat(
        material_id=first,
        repeated_at=helpers.at(helpers.day(-4), 7),
    )
    await helpers.insert_repeat(
        material_id=first,
        repeated_at=helpers.at(helpers.day(-4), 8),
    )
    await helpers.insert_repeat(
        material_id=second,
        repeated_at=helpers.at(helpers.day(-4), 9),
    )
    await helpers.insert_repeat(
        material_id=second,
        repeated_at=helpers.at(LAST_DAY, 23, 59, 59),
    )
    await helpers.insert_repeat(material_id=second, repeated_at=helpers.at(DAY_AFTER))
    return first, second


REPEATS_IN_SPAN = {FIRST_DAY: 1, helpers.day(-4): 3, LAST_DAY: 1}


async def test_repeated_materials_statistics_count_repeats_per_day_inside_the_span():
    await _seed_repeats()

    stat = await trends._calculate_span_repeated_materials_statistics(SPAN)

    assert stat == REPEATS_IN_SPAN


async def _outlined_material(
    *note_dates: datetime.datetime,
    is_outlined: bool = True,
) -> None:
    material_id = await factories.insert_material()
    if is_outlined:
        await materials_db.outline_material(material_id=material_id)
    for added_at in note_dates:
        await _note(material_id, added_at)


async def _seed_outlined_materials() -> None:
    await _outlined_material(helpers.at(FIRST_DAY), helpers.at(helpers.day(-5), 10))
    await _outlined_material(helpers.at(helpers.day(-5), 22))
    await _outlined_material(helpers.at(LAST_DAY, 23, 59, 59))
    # the last note inside the span counts, the later one outside it is ignored
    await _outlined_material(helpers.at(FIRST_DAY, 1), helpers.at(DAY_AFTER))
    await _outlined_material(helpers.at(DAY_BEFORE, 23, 59, 59))
    await _outlined_material(helpers.at(helpers.day(-3)), is_outlined=False)
    await _outlined_material()


OUTLINED_IN_SPAN = {FIRST_DAY: 1, helpers.day(-5): 2, LAST_DAY: 1}


async def test_outlined_materials_statistics_use_the_last_note_inside_the_span():
    await _seed_outlined_materials()

    stat = await trends._calculate_span_outlined_materials_statistics(SPAN)

    assert stat == OUTLINED_IN_SPAN


SPAN_STATISTICS = [
    trends._calculate_span_reading_statistics,
    trends._calculate_span_notes_statistics,
    trends._calculate_span_completed_materials_statistics,
    trends._calculate_span_repeated_materials_statistics,
    trends._calculate_span_outlined_materials_statistics,
]


@pytest.mark.parametrize("calculate", SPAN_STATISTICS, ids=lambda fn: fn.__name__)
async def test_span_statistics_on_an_empty_database_are_empty(calculate):
    assert await calculate(SPAN) == {}


@pytest.mark.parametrize("calculate", SPAN_STATISTICS, ids=lambda fn: fn.__name__)
async def test_span_statistics_ignore_rows_outside_the_span(calculate):
    material_id = await factories.start_material()
    await materials_db.outline_material(material_id=material_id)
    for date in (DAY_BEFORE, DAY_AFTER):
        await _log(material_id, date, 5)
        await _note(material_id, helpers.at(date, 12))
        await _completed(helpers.at(date, 12))
        await helpers.insert_repeat(
            material_id=material_id,
            repeated_at=helpers.at(date, 12),
        )

    assert await calculate(SPAN) == {}


async def test_materials_analytics_group_completions_in_the_span_by_type():
    await _seed_completed_materials()

    analytics = await trends._materials_analytics(SPAN)

    assert analytics == trends._MaterialAnalytics(
        stats={
            enums.MaterialTypesEnum.book: 1,
            enums.MaterialTypesEnum.article: 2,
            enums.MaterialTypesEnum.course: 1,
        },
        total=4,
    )


async def test_materials_analytics_on_an_empty_database_are_zero():
    assert await trends._materials_analytics(SPAN) == trends._MaterialAnalytics(
        stats={},
        total=0,
    )


async def test_reading_analytics_group_pages_read_in_the_span_by_type():
    await _seed_reading_log()

    analytics = await trends._reading_analytics(SPAN)

    assert analytics == trends._MaterialAnalytics(
        stats={enums.MaterialTypesEnum.book: 30, enums.MaterialTypesEnum.article: 12},
        total=42,
    )


async def test_reading_analytics_on_an_empty_database_are_zero():
    assert await trends._reading_analytics(SPAN) == trends._MaterialAnalytics(
        stats={},
        total=0,
    )


async def test_get_repeats_count_counts_repeats_and_distinct_materials_in_the_span():
    await _seed_repeats()

    analytics = await trends._get_repeats_count(SPAN)

    assert analytics == trends._RepeatAnalytics(repeats_count=5, unique_materials_count=2)


async def test_get_repeats_count_on_an_empty_database_is_zero():
    assert await trends._get_repeats_count(SPAN) == trends._RepeatAnalytics(
        repeats_count=0,
        unique_materials_count=0,
    )


async def test_span_total_read_accumulates_from_everything_read_before_the_span():
    await _seed_reading_log()

    total = await trends._calculate_span_total_read(span=SPAN)

    assert total == {
        helpers.day(-6): 1010,
        helpers.day(-5): 1010,
        helpers.day(-4): 1010,
        helpers.day(-3): 1035,
        helpers.day(-2): 1035,
        helpers.day(-1): 1035,
        helpers.day(0): 1042,
    }


async def test_span_total_read_on_an_empty_database_is_zero_for_every_day():
    total = await trends._calculate_span_total_read(span=SPAN)

    assert total == {helpers.day(offset): 0 for offset in range(-6, 1)}


WRAPPERS = {
    "reading": (trends.get_span_reading_statistics, _seed_reading_log, READING_IN_SPAN),
    "notes": (trends.get_span_notes_statistics, _seed_notes, NOTES_IN_SPAN),
    "completed": (
        trends.get_span_completed_materials_statistics,
        _seed_completed_materials,
        COMPLETED_IN_SPAN,
    ),
    "repeated": (
        trends.get_span_repeated_materials_statistics,
        _seed_repeats,
        REPEATS_IN_SPAN,
    ),
    "outlined": (
        trends.get_span_outlined_materials_statistics,
        _seed_outlined_materials,
        OUTLINED_IN_SPAN,
    ),
}


@pytest.mark.parametrize("name", WRAPPERS)
async def test_get_span_statistics_cover_the_days_up_to_today(name):
    get_statistics, seed, expected = WRAPPERS[name]
    await seed()

    stat = await get_statistics(span_size=SPAN_SIZE)

    assert stat.span_size == SPAN_SIZE
    assert stat.data == _days(expected)
    assert (stat.start, stat.stop) == (FIRST_DAY, LAST_DAY)
    assert stat.total == sum(expected.values())
    assert stat.zero_days == SPAN_SIZE - len(expected)


@pytest.mark.parametrize("name", WRAPPERS)
async def test_get_span_statistics_of_one_day_is_today_only(name):
    get_statistics, seed, expected = WRAPPERS[name]
    await seed()

    stat = await get_statistics(span_size=1)

    assert stat.data == [trends.DayStatistics(date=LAST_DAY, amount=expected[LAST_DAY])]


@pytest.mark.parametrize("name", WRAPPERS)
async def test_get_span_statistics_on_an_empty_database_are_all_zero(name):
    get_statistics, _, _ = WRAPPERS[name]

    stat = await get_statistics(span_size=3)

    assert stat.data == _days({}, size=3)
    assert stat.total == 0
    assert stat.mean == Decimal("0.00")
    assert stat.zero_days == 3
    assert (
        stat.max_record
        == stat.min_record
        == trends.DayStatistics(date=helpers.day(-2), amount=0)
    )


@pytest.mark.parametrize("name", WRAPPERS)
async def test_get_span_statistics_reject_an_empty_span(name):
    get_statistics, _, _ = WRAPPERS[name]

    with pytest.raises(trends.TrendException, match="Start is better than stop"):
        await get_statistics(span_size=0)


async def test_get_span_reading_statistics_derives_the_aggregates():
    await _seed_reading_log()

    stat = await trends.get_span_reading_statistics(span_size=SPAN_SIZE)

    assert stat.dump() == {
        "total": 42,
        "median": 0,
        "mean": Decimal("6.00"),
        "lost_count": 24,
        "zero_days": 4,
        "would_be_total": 66,
    }
    assert stat.max_record == trends.DayStatistics(date=helpers.day(-3), amount=25)
    assert stat.min_record == trends.DayStatistics(date=LAST_DAY, amount=7)


async def test_get_span_total_read_statistics_covers_the_days_up_to_today():
    await _seed_reading_log()

    total = await trends.get_span_total_read_statistics(span_size=3)

    assert total == {helpers.day(-2): 1035, helpers.day(-1): 1035, helpers.day(0): 1042}


def _report_request() -> schemas.GetSpanReportRequest:
    return schemas.GetSpanReportRequest(start=FIRST_DAY, stop=LAST_DAY)


async def test_get_span_analytics_combines_every_statistic():
    await _seed_reading_log()
    await _seed_notes()
    await _seed_completed_materials()
    await _seed_repeats()

    analysis = await trends.get_span_analytics(_report_request())

    assert analysis.reading.data == _days(READING_IN_SPAN)
    assert analysis.notes.data == _days(NOTES_IN_SPAN)
    assert analysis.materials_analytics.total == 4
    assert analysis.reading_analytics == trends._MaterialAnalytics(
        stats={enums.MaterialTypesEnum.book: 30, enums.MaterialTypesEnum.article: 12},
        total=42,
    )
    assert analysis.repeat_analytics == trends._RepeatAnalytics(
        repeats_count=5,
        unique_materials_count=2,
    )


async def test_get_span_analytics_on_an_empty_database():
    analysis = await trends.get_span_analytics(_report_request())

    assert analysis.reading.total == 0
    assert analysis.notes.total == 0


async def test_get_span_analytics_gives_the_whole_analysis():
    await _seed_reading_log()
    await _seed_notes()
    await _seed_completed_materials()
    await _seed_repeats()

    analysis = await trends.get_span_analytics(_report_request())

    assert analysis == trends.SpanAnalysis(
        reading=trends.SpanStatistics(data=_days(READING_IN_SPAN), span_size=SPAN_SIZE),
        notes=trends.SpanStatistics(data=_days(NOTES_IN_SPAN), span_size=SPAN_SIZE),
        materials_analytics=trends._MaterialAnalytics(
            stats={
                enums.MaterialTypesEnum.book: 1,
                enums.MaterialTypesEnum.article: 2,
                enums.MaterialTypesEnum.course: 1,
            },
            total=4,
        ),
        reading_analytics=trends._MaterialAnalytics(
            stats={enums.MaterialTypesEnum.book: 30, enums.MaterialTypesEnum.article: 12},
            total=42,
        ),
        repeat_analytics=trends._RepeatAnalytics(
            repeats_count=5,
            unique_materials_count=2,
        ),
    )


def _is_svg(image: str) -> bool:
    return base64.b64decode(image).startswith(b"<?xml")


async def test_reading_graphic_marks_completion_days_green(mocker):
    await _seed_reading_log()
    stat = await trends.get_span_reading_statistics(span_size=3)
    barh = mocker.spy(Axes, "barh")

    image = trends.create_reading_graphic(
        stat,
        completion_dates={
            uuid.uuid4(): helpers.at(helpers.day(-1), 18),
            None: helpers.at(DAY_BEFORE),
        },
    )

    assert _is_svg(image)
    assert barh.call_args.args[1:] == (
        [helpers.day(offset).strftime("%Y-%m-%d") for offset in (-2, -1, 0)],
        [0, 0, 7],
    )
    assert barh.call_args.kwargs["color"] == ["steelblue", "green", "steelblue"]


@pytest.mark.parametrize("completion_dates", [None, {}], ids=["none", "empty"])
async def test_reading_graphic_without_completion_dates_uses_the_default_colour(
    mocker,
    completion_dates,
):
    await _seed_reading_log()
    stat = await trends.get_span_reading_statistics(span_size=SPAN_SIZE)
    barh = mocker.spy(Axes, "barh")
    axvline = mocker.spy(Axes, "axvline")

    image = trends.create_reading_graphic(stat, completion_dates=completion_dates)

    assert _is_svg(image)
    assert barh.call_args.kwargs["color"] is None
    assert axvline.call_args.kwargs["x"] == 6.0


GRAPHICS = {
    "notes": (trends.create_notes_graphic, "Total notes inserted"),
    "completed": (trends.create_completed_materials_graphic, "Total materials completed"),
    "repeated": (trends.create_repeated_materials_graphic, "Total materials repeated"),
    "outlined": (trends.create_outlined_materials_graphic, "Total materials outlined"),
}


@pytest.mark.parametrize("name", GRAPHICS)
@pytest.mark.parametrize("is_seeded", [True, False], ids=["with-rows", "empty-database"])
async def test_span_graphics_are_drawn_from_the_statistics(mocker, name, is_seeded):
    get_statistics, seed, expected = WRAPPERS[name]
    create_graphic, title = GRAPHICS[name]
    if is_seeded:
        await seed()
    stat = await get_statistics(span_size=SPAN_SIZE)
    set_title = mocker.spy(Axes, "set_title")
    set_xlim = mocker.spy(Axes, "set_xlim")

    image = create_graphic(stat)

    assert _is_svg(image)
    assert set_title.call_args.args[1] == title
    highest = max(expected.values()) if is_seeded else 0
    # an all-zero span falls back to a fixed axis width
    assert set_xlim.call_args.args[1] == pytest.approx(
        (-highest / 100, highest * 1.15 or 100),
    )


async def test_total_read_graphic_is_drawn_from_the_statistics(mocker):
    await _seed_reading_log()
    stat = await trends.get_span_total_read_statistics(span_size=3)
    plot = mocker.spy(Axes, "plot")

    image = trends.create_total_read_graphic(stat)

    assert _is_svg(image)
    assert plot.call_args.args[1:] == (
        [helpers.day(offset).strftime("%Y-%m-%d") for offset in (-2, -1, 0)],
        [1035, 1035, 1042],
    )


async def test_span_statistics_render_as_text():
    await _seed_reading_log()

    stat = await trends.get_span_reading_statistics(span_size=2)

    assert str(stat) == f"{helpers.day(-1)}: 0\n{LAST_DAY}: 7"
    assert stat.days == [str(helpers.day(-1)), str(LAST_DAY)]
    assert stat.values == [0, 7]
    assert stat.data[1].format() == str(LAST_DAY)


def test_span_statistics_reject_a_size_that_differs_from_the_data():
    with pytest.raises(
        trends.TrendException,
        match="Wrong span size: expected=2, found=1",
    ):
        trends.SpanStatistics(data=_days({}, size=1), span_size=2)


@pytest.mark.parametrize("edge", ["start", "stop"])
def test_empty_span_statistics_have_no_edges(edge):
    stat = trends.SpanStatistics(data=[], span_size=0)

    with pytest.raises(trends.TrendException, match="Span statistics is empty"):
        getattr(stat, edge)


def test_time_span_renders_and_iterates_its_inclusive_days():
    assert SPAN.format() == f"{FIRST_DAY}_{LAST_DAY}"
    assert str(SPAN) == f"[{FIRST_DAY}; {LAST_DAY}]"
    assert list(SPAN.iter()) == [helpers.day(offset) for offset in range(-6, 1)]
    assert list(trends._iterate_over_span(SPAN, size=2)) == [FIRST_DAY, helpers.day(-5)]


def test_time_span_rejects_a_size_that_differs_from_the_dates():
    with pytest.raises(trends.TrendException, match="Wrong span got"):
        trends.TimeSpan(start=FIRST_DAY, stop=LAST_DAY, span_size=SPAN_SIZE + 1)


def test_report_request_defaults_to_today_and_shifts_back():
    request = _report_request()

    earlier = request.create_span_ago(7)

    assert request.size == SPAN_SIZE
    assert (earlier.start, earlier.stop) == (helpers.day(-13), helpers.day(-7))
    with pytest.raises(ValueError, match="Ago must be > 0, 0 found"):
        request.create_span_ago(0)
    assert (
        schemas.GetSpanReportRequest(start=datetime.date(2000, 1, 1)).stop
        == schemas._now()
    )


async def test_graphic_without_the_mean_line_has_no_legend(mocker):
    await _seed_reading_log()
    stat = await trends.get_span_reading_statistics(span_size=SPAN_SIZE)
    axvline = mocker.spy(Axes, "axvline")
    legend = mocker.spy(Axes, "legend")

    image = trends._create_graphic(stat=stat, show_mean_line=False)

    assert _is_svg(image)
    assert axvline.call_count == 0
    assert legend.call_count == 0
