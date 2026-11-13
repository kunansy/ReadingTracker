import datetime
from uuid import UUID

import matplotlib.pyplot as plt
import pytest

from tests.unit.system.conftest import decode_svg, frozen_datetime_module
from tracker.common import settings
from tracker.materials import db as materials_db
from tracker.models import enums
from tracker.reading_log import db as logs_db
from tracker.system import db


D = datetime.date
MATERIAL_ID = UUID(int=1)
OTHER_MATERIAL_ID = UUID(int=2)
Types = enums.MaterialTypesEnum


def _record(day: int, count: int, material_id: UUID = MATERIAL_ID):
    date = D(2024, 1, day)
    return date, logs_db.LogRecord(date=date, count=count, material_id=material_id)


@pytest.fixture
def reading_log(mocker):
    def install(records: list) -> None:
        async def data():
            for record in records:
                yield record

        mocker.patch.object(logs_db, "data", data)

    return install


@pytest.fixture
def axes(mocker):
    subplots = mocker.spy(plt, "subplots")
    return lambda: subplots.spy_return[1]


class TestGetGraphicData:
    async def test_no_logs_give_empty_data(self, reading_log):
        reading_log([])

        result = await db._get_graphic_data(material_id=MATERIAL_ID, last_days=7)

        assert result == db.ReadingData(counts=[], dates=[])

    async def test_fewer_days_than_requested_are_all_returned(self, reading_log):
        reading_log([_record(1, 10), _record(2, 5)])

        result = await db._get_graphic_data(material_id=MATERIAL_ID, last_days=7)

        assert result == db.ReadingData(counts=[10, 15], dates=[D(2024, 1, 1), D(2024, 1, 2)])

    async def test_exactly_the_requested_days_are_all_returned(self, reading_log):
        reading_log([_record(1, 10), _record(2, 5), _record(3, 1)])

        result = await db._get_graphic_data(material_id=MATERIAL_ID, last_days=3)

        assert result == db.ReadingData(
            counts=[10, 15, 16],
            dates=[D(2024, 1, 1), D(2024, 1, 2), D(2024, 1, 3)],
        )

    async def test_more_days_than_requested_keep_the_last_ones_with_full_totals(
        self,
        reading_log,
    ):
        reading_log([_record(1, 10), _record(2, 5), _record(3, 1), _record(4, 4)])

        result = await db._get_graphic_data(material_id=MATERIAL_ID, last_days=2)

        assert result == db.ReadingData(counts=[16, 20], dates=[D(2024, 1, 3), D(2024, 1, 4)])

    async def test_last_day_only(self, reading_log):
        reading_log([_record(1, 10), _record(2, 5)])

        result = await db._get_graphic_data(material_id=MATERIAL_ID, last_days=1)

        assert result == db.ReadingData(counts=[15], dates=[D(2024, 1, 2)])

    async def test_other_materials_are_skipped(self, reading_log):
        reading_log(
            [
                _record(1, 10),
                _record(2, 100, OTHER_MATERIAL_ID),
                _record(3, 5),
                _record(4, 100, OTHER_MATERIAL_ID),
            ],
        )

        result = await db._get_graphic_data(material_id=MATERIAL_ID, last_days=7)

        assert result == db.ReadingData(counts=[10, 15], dates=[D(2024, 1, 1), D(2024, 1, 3)])

    async def test_material_without_logs_gives_empty_data(self, reading_log):
        reading_log([_record(1, 10, OTHER_MATERIAL_ID)])

        result = await db._get_graphic_data(material_id=MATERIAL_ID, last_days=7)

        assert result == db.ReadingData(counts=[], dates=[])

    async def test_zero_count_days_repeat_the_total(self, reading_log):
        reading_log([_record(1, 10), _record(2, 0), _record(3, 0)])

        result = await db._get_graphic_data(material_id=MATERIAL_ID, last_days=7)

        assert result.counts == [10, 10, 10]


class TestSetPlotStyle:
    @pytest.mark.parametrize(
        ("now", "style"),
        [
            (datetime.time(0, 0, 0), "default"),
            (datetime.time(14, 59, 59), "default"),
            (datetime.time(15, 0, 0), "dark_background"),
            (datetime.time(23, 59, 59), "dark_background"),
        ],
        ids=["midnight", "second-before", "exactly-at", "end-of-day"],
    )
    def test_dark_style_starts_at_the_configured_time(self, mocker, now, style):
        mocker.patch.object(settings, "EX_DARKMODE_ENABLE", datetime.time(15, 0, 0))
        mocker.patch.object(
            db,
            "datetime",
            frozen_datetime_module(datetime.datetime.combine(D(2024, 1, 1), now)),
        )
        use_style = mocker.patch.object(plt.style, "use")

        db._set_plot_style()

        use_style.assert_called_once_with(style)

    def test_pinned_setting(self):
        assert settings.EX_DARKMODE_ENABLE == datetime.time(15, 0, 0)


class TestCreateReadingGraphic:
    @pytest.fixture(autouse=True)
    def plot_style(self, mocker):
        return mocker.patch.object(db, "_set_plot_style")

    @pytest.fixture
    def material(self, mocker):
        def install(pages: int):
            return mocker.patch.object(
                materials_db,
                "get_material_api",
                mocker.AsyncMock(return_value=mocker.Mock(pages=pages)),
            )

        return install

    async def test_returns_base64_svg(self, material, reading_log, plot_style):
        get_material = material(100)
        reading_log([_record(1, 10), _record(2, 20)])

        image = await db.create_reading_graphic(material_id=MATERIAL_ID, last_days=7)

        svg = decode_svg(image)
        assert svg.startswith("<?xml")
        assert "<svg" in svg
        get_material.assert_awaited_once_with(material_id=MATERIAL_ID)
        plot_style.assert_called_once_with()

    async def test_unfinished_material_shows_remaining_pages(
        self,
        material,
        reading_log,
        axes,
    ):
        material(100)
        reading_log([_record(1, 10), _record(2, 20)])

        await db.create_reading_graphic(material_id=MATERIAL_ID, last_days=7)

        ax = axes()
        assert [bar.get_height() for bar in ax.patches] == [10, 30]
        assert [text.get_text() for text in ax.get_legend().get_texts()] == [
            "Overall 100 items",
            "70 items remains",
        ]
        assert ax.get_ylim() == (0, pytest.approx(110))
        assert ax.get_title() == "Total items completed"
        assert ax.get_xlabel() == "Date"
        assert ax.get_ylabel() == "Items count"

    @pytest.mark.parametrize("pages", [30, 25], ids=["exactly-read", "over-read"])
    async def test_finished_material_has_no_remaining_line(
        self,
        material,
        reading_log,
        axes,
        pages,
    ):
        material(pages)
        reading_log([_record(1, 10), _record(2, 20)])

        await db.create_reading_graphic(material_id=MATERIAL_ID, last_days=7)

        legend = axes().get_legend()
        assert [text.get_text() for text in legend.get_texts()] == [f"Overall {pages} items"]

    async def test_last_days_limit_the_bars_but_not_the_total(
        self,
        material,
        reading_log,
        axes,
    ):
        material(100)
        reading_log([_record(1, 10), _record(2, 20), _record(3, 30)])

        await db.create_reading_graphic(material_id=MATERIAL_ID, last_days=1)

        ax = axes()
        assert [bar.get_height() for bar in ax.patches] == [60]
        assert ax.get_legend().get_texts()[1].get_text() == "40 items remains"

    @pytest.mark.xfail(
        strict=True,
        raises=IndexError,
        reason=(
            "BUG: tracker/system/db.py:50 data.counts[-1] raises IndexError for a "
            "material that has no reading log yet"
        ),
    )
    async def test_material_without_logs_is_rendered(self, material, reading_log):
        material(100)
        reading_log([])

        image = await db.create_reading_graphic(material_id=MATERIAL_ID, last_days=7)

        assert "<svg" in decode_svg(image)

    async def test_missing_material_error_is_propagated(self, mocker, reading_log):
        mocker.patch.object(
            materials_db,
            "get_material_api",
            mocker.AsyncMock(side_effect=ValueError("not found")),
        )
        reading_log([])

        with pytest.raises(ValueError, match="not found"):
            await db.create_reading_graphic(material_id=MATERIAL_ID, last_days=7)

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "BUG: tracker/system/db.py:54 the figure is never closed, so every "
            "rendered graphic stays registered in pyplot (memory leak)"
        ),
    )
    async def test_figure_is_closed_after_rendering(self, material, reading_log):
        material(100)
        reading_log([_record(1, 10)])

        await db.create_reading_graphic(material_id=MATERIAL_ID, last_days=7)

        assert plt.get_fignums() == []


def _every_type(counts: dict[bool, int]) -> dict[Types, dict[bool, int]]:
    return {material_type: dict(counts) for material_type in Types}


class TestCreateOutlinePercentageGraphic:
    @pytest.fixture(autouse=True)
    def plot_style(self, mocker):
        return mocker.patch.object(db, "_set_plot_style")

    @pytest.fixture
    def outline(self, mocker):
        def install(stat: dict[Types, dict[bool, int]]):
            return mocker.patch.object(
                db,
                "_calculate_outline_percentage",
                mocker.AsyncMock(return_value=stat),
            )

        return install

    @staticmethod
    def _bars(ax) -> dict[str, list[float]]:
        return {
            container.get_label(): [bar.get_height() for bar in container]
            for container in ax.containers
        }

    async def test_returns_base64_svg(self, outline, plot_style):
        outline(_every_type({True: 1, False: 3}))

        image = await db.create_outline_percentage_graphic()

        svg = decode_svg(image)
        assert svg.startswith("<?xml")
        assert "<svg" in svg
        plot_style.assert_called_once_with()

    async def test_bars_are_percentages_per_material_type_in_name_order(self, outline, axes):
        outline(
            {
                Types.book: {True: 1, False: 3},
                Types.article: {True: 1, False: 1},
                Types.course: {False: 1, True: 2},
                Types.lecture: {True: 9, False: 1},
                Types.audiobook: {True: 1, False: 9},
            },
        )

        await db.create_outline_percentage_graphic()

        ax = axes()
        assert [label.get_text() for label in ax.get_xticklabels()] == [
            "article",
            "audiobook",
            "book",
            "course",
            "lecture",
        ]
        bars = self._bars(ax)
        assert bars["outlined"] == pytest.approx([50, 10, 25, 66.67, 90])
        assert bars["not_outlined"] == pytest.approx([50, 90, 75, 33.33, 10])
        assert ax.get_title() == "Outline percentage"

    @pytest.mark.xfail(
        strict=True,
        raises=ValueError,
        reason=(
            "BUG: tracker/system/db.py:126-141 a type whose completed materials are "
            "all outlined has no False entry, the two lists get out of step and "
            "ax.bar() fails with a shape mismatch"
        ),
    )
    async def test_type_with_only_outlined_materials_is_100_percent(self, outline, axes):
        outline(_every_type({True: 1, False: 1}) | {Types.book: {True: 5}})

        await db.create_outline_percentage_graphic()

        bars = self._bars(axes())
        assert bars["outlined"] == pytest.approx([50, 50, 100, 50, 50])
        assert bars["not_outlined"] == pytest.approx([50, 50, 0, 50, 50])

    @pytest.mark.xfail(
        strict=True,
        raises=ValueError,
        reason=(
            "BUG: tracker/system/db.py:126-141 a type whose completed materials are "
            "all not outlined has no True entry, the two lists get out of step and "
            "ax.bar() fails with a shape mismatch"
        ),
    )
    async def test_type_with_only_not_outlined_materials_is_0_percent(self, outline, axes):
        outline(_every_type({True: 1, False: 1}) | {Types.book: {False: 5}})

        await db.create_outline_percentage_graphic()

        bars = self._bars(axes())
        assert bars["outlined"] == pytest.approx([50, 50, 0, 50, 50])
        assert bars["not_outlined"] == pytest.approx([50, 50, 100, 50, 50])

    @pytest.mark.xfail(
        strict=True,
        raises=AssertionError,
        reason=(
            "BUG: tracker/system/db.py:117-118 a material type with no completed "
            "materials is missing from the statistics, so the species assertion "
            "fails (or, for the first type only, its bar is copied to every type)"
        ),
    )
    async def test_type_without_completed_materials_has_empty_bars(self, outline, axes):
        outline({Types.book: {True: 1, False: 3}})

        await db.create_outline_percentage_graphic()

        bars = self._bars(axes())
        assert bars["outlined"] == pytest.approx([0, 0, 25, 0, 0])
        assert bars["not_outlined"] == pytest.approx([0, 0, 75, 0, 0])

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "BUG: tracker/system/db.py:117,152 when only the alphabetically first "
            "type has completed materials its single bar is broadcast to all types"
        ),
    )
    async def test_only_first_type_completed_does_not_fill_other_types(self, outline, axes):
        outline({Types.article: {True: 1, False: 3}})

        await db.create_outline_percentage_graphic()

        assert self._bars(axes())["outlined"] == pytest.approx([25, 0, 0, 0, 0])

    @pytest.mark.xfail(
        strict=True,
        raises=ValueError,
        reason=(
            "BUG: tracker/system/db.py:152 with no completed materials at all the "
            "count lists are empty and ax.bar() fails with a shape mismatch"
        ),
    )
    async def test_no_completed_materials_are_rendered(self, outline):
        outline({})

        image = await db.create_outline_percentage_graphic()

        assert "<svg" in decode_svg(image)

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "BUG: tracker/system/db.py:123 the figure is never closed, so every "
            "rendered graphic stays registered in pyplot (memory leak)"
        ),
    )
    async def test_figure_is_closed_after_rendering(self, outline):
        outline(_every_type({True: 1, False: 3}))

        await db.create_outline_percentage_graphic()

        assert plt.get_fignums() == []
