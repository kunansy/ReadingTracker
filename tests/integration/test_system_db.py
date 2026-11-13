import base64
import datetime
import uuid

import pytest
from matplotlib.axes import Axes

from tests.integration import (
    factories,
    helpers_notes as helpers,
)
from tracker.common import database, settings
from tracker.materials import db as materials_db
from tracker.models import enums
from tracker.system import db as system_db


MISSING_ID = uuid.UUID("00000000-0000-4000-8000-000000000000")


@pytest.fixture(autouse=True)
def frozen_clock(mocker) -> None:
    mocker.patch.object(database, "utcnow", return_value=helpers.FROZEN_NOW)


async def _material_with_logs(*, pages: int = 100) -> uuid.UUID:
    """Read 10, 20 and 5 pages five, four and two days before the frozen today."""
    material_id = await factories.start_material(pages=pages, started_days_ago=6)
    for days_ago, count in [(5, 10), (4, 20), (2, 5)]:
        await factories.insert_log(
            material_id=material_id,
            count=count,
            date=helpers.day(-days_ago),
        )
    return material_id


def _is_svg(image: str) -> bool:
    return base64.b64decode(image).startswith(b"<?xml")


async def test_get_graphic_data_accumulates_pages_over_every_day_up_to_today():
    material_id = await _material_with_logs()

    data = await system_db._get_graphic_data(material_id=material_id, last_days=100)

    assert data == system_db.ReadingData(
        counts=[10, 30, 30, 35, 35, 35],
        dates=[helpers.day(offset) for offset in range(-5, 1)],
    )


@pytest.mark.parametrize(
    ("last_days", "expected_counts"),
    [
        (1, [35]),
        (2, [35, 35]),
        (5, [30, 30, 35, 35, 35]),
        (6, [10, 30, 30, 35, 35, 35]),
        (7, [10, 30, 30, 35, 35, 35]),
    ],
    ids=["one", "two", "one-less-than-the-log", "exactly-the-log", "more-than-the-log"],
)
async def test_get_graphic_data_keeps_the_last_days(last_days, expected_counts):
    material_id = await _material_with_logs()

    data = await system_db._get_graphic_data(material_id=material_id, last_days=last_days)

    assert data.counts == expected_counts
    assert data.dates == [
        helpers.day(offset) for offset in range(1 - len(expected_counts), 1)
    ]


async def test_get_graphic_data_with_zero_last_days_returns_everything_current_behaviour():
    material_id = await _material_with_logs()

    data = await system_db._get_graphic_data(material_id=material_id, last_days=0)

    # counts[-0:] is the whole list
    assert data.counts == [10, 30, 30, 35, 35, 35]


async def test_get_graphic_data_skips_days_of_other_materials():
    first = await factories.start_material(started_days_ago=6)
    second = await factories.start_material(started_days_ago=6)
    await factories.insert_log(material_id=first, count=10, date=helpers.day(-5))
    await factories.insert_log(material_id=first, count=20, date=helpers.day(-4))
    await factories.insert_log(material_id=second, count=7, date=helpers.day(-3))
    await factories.insert_log(material_id=first, count=5, date=helpers.day(-2))

    first_data = await system_db._get_graphic_data(material_id=first, last_days=100)
    second_data = await system_db._get_graphic_data(material_id=second, last_days=100)

    assert first_data == system_db.ReadingData(
        counts=[10, 30, 35, 35, 35],
        dates=[
            helpers.day(-5),
            helpers.day(-4),
            helpers.day(-2),
            helpers.day(-1),
            helpers.day(0),
        ],
    )
    assert second_data == system_db.ReadingData(counts=[7], dates=[helpers.day(-3)])


async def test_get_graphic_data_sums_two_materials_read_on_the_same_day():
    first = await factories.start_material(started_days_ago=3)
    second = await factories.start_material(started_days_ago=3)
    await factories.insert_log(material_id=first, count=4, date=helpers.day(0))
    await factories.insert_log(material_id=second, count=6, date=helpers.day(0))

    assert await system_db._get_graphic_data(material_id=first, last_days=5) == (
        [4],
        [helpers.day(0)],
    )
    assert await system_db._get_graphic_data(material_id=second, last_days=5) == (
        [6],
        [helpers.day(0)],
    )


async def test_get_graphic_data_of_a_material_without_logs_is_empty():
    await _material_with_logs()
    without_logs = await factories.start_material()

    data = await system_db._get_graphic_data(material_id=without_logs, last_days=7)

    assert data == system_db.ReadingData(counts=[], dates=[])


async def test_get_graphic_data_on_an_empty_database_is_empty():
    data = await system_db._get_graphic_data(material_id=MISSING_ID, last_days=7)

    assert data == system_db.ReadingData(counts=[], dates=[])


@pytest.mark.parametrize("last_days", [2, 6, 100], ids=["smaller", "equal", "larger"])
async def test_create_reading_graphic_marks_the_remaining_pages(mocker, last_days):
    material_id = await _material_with_logs(pages=100)
    vlines = mocker.spy(Axes, "vlines")
    bar = mocker.spy(Axes, "bar")

    image = await system_db.create_reading_graphic(
        material_id=material_id,
        last_days=last_days,
    )

    assert _is_svg(image)
    assert vlines.call_count == 1
    assert vlines.call_args.kwargs["label"] == "65 items remains"
    assert vlines.call_args.kwargs["ymax"] == 100
    expected_counts = [10, 30, 30, 35, 35, 35][-last_days:]
    assert bar.call_args.args[2] == expected_counts
    assert bar.call_args.args[1] == [
        helpers.day(offset) for offset in range(1 - len(expected_counts), 1)
    ]


async def test_create_reading_graphic_of_a_fully_read_material_has_no_remains_line(
    mocker,
):
    material_id = await _material_with_logs(pages=35)
    vlines = mocker.spy(Axes, "vlines")

    image = await system_db.create_reading_graphic(material_id=material_id, last_days=7)

    assert _is_svg(image)
    assert vlines.call_count == 0


@pytest.mark.parametrize(
    ("darkmode_from", "style"),
    [(datetime.time.min, "dark_background"), (datetime.time.max, "default")],
    ids=["dark", "light"],
)
async def test_create_reading_graphic_picks_the_style_by_the_dark_mode_hour(
    mocker,
    darkmode_from,
    style,
):
    material_id = await _material_with_logs()
    mocker.patch.object(settings, "EX_DARKMODE_ENABLE", darkmode_from)
    use_style = mocker.spy(system_db.plt.style, "use")

    await system_db.create_reading_graphic(material_id=material_id, last_days=7)

    use_style.assert_called_once_with(style)


async def test_create_reading_graphic_raises_not_found_for_a_missing_material():
    with pytest.raises(database.NotFoundException, match=str(MISSING_ID)):
        await system_db.create_reading_graphic(material_id=MISSING_ID, last_days=7)


@pytest.mark.xfail(
    strict=True,
    raises=IndexError,
    reason="BUG: tracker/system/db.py:50 data.counts[-1] raises IndexError "
    "for a material that has no reading log yet",
)
async def test_create_reading_graphic_of_a_material_without_logs():
    material_id = await factories.start_material(pages=50)

    image = await system_db.create_reading_graphic(material_id=material_id, last_days=7)

    assert _is_svg(image)


async def _complete(
    material_type: enums.MaterialTypesEnum,
    *,
    outlined: int,
    not_outlined: int,
):
    for index in range(outlined + not_outlined):
        material_id = await factories.complete_material(material_type=material_type)
        if index < outlined:
            await materials_db.outline_material(material_id=material_id)


async def test_calculate_outline_percentage_counts_completed_materials_by_type():
    await _complete(enums.MaterialTypesEnum.book, outlined=2, not_outlined=1)
    await _complete(enums.MaterialTypesEnum.article, outlined=0, not_outlined=3)
    await _complete(enums.MaterialTypesEnum.course, outlined=1, not_outlined=0)
    queued = await factories.insert_material(
        material_type=enums.MaterialTypesEnum.lecture,
    )
    reading = await factories.start_material(
        material_type=enums.MaterialTypesEnum.audiobook,
    )
    await materials_db.outline_material(material_id=queued)
    await materials_db.outline_material(material_id=reading)

    stat = await system_db._calculate_outline_percentage()

    assert stat == {
        enums.MaterialTypesEnum.book: {True: 2, False: 1},
        enums.MaterialTypesEnum.article: {False: 3},
        enums.MaterialTypesEnum.course: {True: 1},
    }


async def test_calculate_outline_percentage_on_an_empty_database_is_empty():
    assert await system_db._calculate_outline_percentage() == {}


async def test_create_outline_percentage_graphic_stacks_the_percents_of_every_type(
    mocker,
):
    counts = {
        enums.MaterialTypesEnum.article: (1, 3),
        enums.MaterialTypesEnum.audiobook: (1, 1),
        enums.MaterialTypesEnum.book: (3, 1),
        enums.MaterialTypesEnum.course: (1, 2),
        enums.MaterialTypesEnum.lecture: (2, 2),
    }
    for material_type, (outlined, not_outlined) in counts.items():
        await _complete(material_type, outlined=outlined, not_outlined=not_outlined)
    bar = mocker.spy(Axes, "bar")

    image = await system_db.create_outline_percentage_graphic()

    assert _is_svg(image)
    outlined_call, not_outlined_call = bar.call_args_list
    species = ["article", "audiobook", "book", "course", "lecture"]
    assert outlined_call.args[1] == species
    assert outlined_call.args[2] == pytest.approx([25.0, 50.0, 75.0, 33.33, 50.0])
    assert outlined_call.kwargs["label"] == "outlined"
    assert not_outlined_call.args[1] == species
    assert not_outlined_call.args[2] == pytest.approx([75.0, 50.0, 25.0, 66.67, 50.0])
    assert not_outlined_call.kwargs["label"] == "not_outlined"


OUTLINE_BUG = (
    "BUG: tracker/system/db.py:117-141 the graphic needs every material type to have both "
    "outlined and not outlined completed materials, otherwise the lists get out of step"
)


@pytest.mark.xfail(strict=True, reason=OUTLINE_BUG)
async def test_create_outline_percentage_graphic_on_an_empty_database():
    assert _is_svg(await system_db.create_outline_percentage_graphic())


@pytest.mark.xfail(strict=True, reason=OUTLINE_BUG)
@pytest.mark.parametrize(
    ("outlined", "not_outlined"),
    [(2, 0), (0, 2)],
    ids=["only-outlined", "only-not-outlined"],
)
async def test_create_outline_percentage_graphic_with_a_type_having_one_kind(
    mocker,
    outlined,
    not_outlined,
):
    for material_type in enums.MaterialTypesEnum:
        if material_type == enums.MaterialTypesEnum.book:
            await _complete(material_type, outlined=outlined, not_outlined=not_outlined)
        else:
            await _complete(material_type, outlined=1, not_outlined=1)
    bar = mocker.spy(Axes, "bar")

    image = await system_db.create_outline_percentage_graphic()

    assert _is_svg(image)
    book_percent = 100.0 if outlined else 0.0
    assert bar.call_args_list[0].args[2] == pytest.approx(
        [50.0, 50.0, book_percent, 50.0, 50.0],
    )


@pytest.mark.xfail(strict=True, reason=OUTLINE_BUG)
async def test_create_outline_percentage_graphic_with_a_type_never_completed(mocker):
    for material_type in enums.MaterialTypesEnum:
        if material_type != enums.MaterialTypesEnum.article:
            await _complete(material_type, outlined=1, not_outlined=1)
    bar = mocker.spy(Axes, "bar")

    image = await system_db.create_outline_percentage_graphic()

    assert _is_svg(image)
    assert bar.call_args_list[0].args[2] == pytest.approx([0.0, 50.0, 50.0, 50.0, 50.0])
