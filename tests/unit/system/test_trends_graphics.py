import datetime
import decimal

import matplotlib.pyplot as plt
import pytest

from tests.unit.system.conftest import build_statistics, decode_svg
from tracker.system import trends


D = datetime.date
GREEN = "fill: #008000"
STEELBLUE = "fill: #4682b4"
LEGEND = '<g id="legend_1">'

WRAPPERS = [
    (trends.create_reading_graphic, "Total pages read"),
    (trends.create_notes_graphic, "Total notes inserted"),
    (trends.create_completed_materials_graphic, "Total materials completed"),
    (trends.create_repeated_materials_graphic, "Total materials repeated"),
    (trends.create_outlined_materials_graphic, "Total materials outlined"),
]


@pytest.fixture
def axes(mocker):
    """The axes of the figure the code under test creates."""
    subplots = mocker.spy(plt, "subplots")
    return lambda: subplots.spy_return[1]


@pytest.mark.parametrize(("create", "title"), WRAPPERS, ids=[title for _, title in WRAPPERS])
class TestCreateSpanGraphics:
    def test_returns_base64_svg_with_the_title(self, axes, create, title):
        image = create(build_statistics([3, 0, 7]))

        svg = decode_svg(image)
        assert svg.startswith("<?xml")
        assert "<svg" in svg
        assert axes().get_title() == title

    def test_single_day(self, axes, create, title):
        svg = decode_svg(create(build_statistics([5])))

        assert "<svg" in svg
        assert [label.get_text() for label in axes().get_yticklabels()] == ["2024-01-01"]

    def test_all_zero_days(self, axes, create, title):
        svg = decode_svg(create(build_statistics([0, 0, 0])))

        assert "<svg" in svg
        assert axes().get_xlim() == (0, 100)

    def test_empty_statistics_raise_current_behaviour(self, create, title):
        with pytest.raises(decimal.InvalidOperation):
            create(build_statistics([]))


class TestCreateGraphic:
    def test_axes_describe_the_statistics(self, axes):
        trends._create_graphic(stat=build_statistics([200, 50]))

        ax = axes()
        assert ax.get_title() == "Total items completed"
        assert ax.get_xlabel() == "Items count"
        assert ax.get_ylabel() == "Date"
        assert ax.get_xlim() == (-2, 230)
        assert ax.yaxis_inverted()
        assert [label.get_text() for label in ax.get_yticklabels()] == [
            "2024-01-01",
            "2024-01-02",
        ]
        assert [bar.get_width() for bar in ax.patches] == [200, 50]

    def test_mean_line_is_labelled_in_the_legend(self, axes):
        svg = decode_svg(trends._create_graphic(stat=build_statistics([1, 2])))

        legend = axes().get_legend()
        assert [text.get_text() for text in legend.get_texts()] == ["Mean 1.50 items"]
        assert [line.get_xdata()[0] for line in axes().lines] == [1.5]
        assert LEGEND in svg

    def test_mean_line_can_be_hidden(self, axes):
        image = trends._create_graphic(stat=build_statistics([1, 2]), show_mean_line=False)

        assert axes().get_legend() is None
        assert list(axes().lines) == []
        assert LEGEND not in decode_svg(image)

    def test_completion_days_are_green(self):
        stat = build_statistics([1, 2, 3])
        completion_dates = {"material": datetime.datetime(2024, 1, 2, 10)}  # noqa: DTZ001

        svg = decode_svg(
            trends.create_reading_graphic(stat, completion_dates=completion_dates),
        )

        assert svg.count(GREEN) == 1
        assert svg.count(STEELBLUE) == 2

    @pytest.mark.parametrize("completion_dates", [None, {}])
    def test_without_completion_dates_default_color_is_used(self, completion_dates):
        stat = build_statistics([1, 2, 3])

        svg = decode_svg(
            trends.create_reading_graphic(stat, completion_dates=completion_dates),
        )

        assert GREEN not in svg
        assert STEELBLUE not in svg

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "BUG: tracker/system/trends.py:532 the figure is never closed, so every "
            "rendered graphic stays registered in pyplot (memory leak)"
        ),
    )
    def test_figure_is_closed_after_rendering(self):
        trends._create_graphic(stat=build_statistics([1, 2]))

        assert plt.get_fignums() == []

    def test_every_call_leaves_one_more_open_figure_current_behaviour(self):
        trends._create_graphic(stat=build_statistics([1, 2]))
        trends._create_graphic(stat=build_statistics([1, 2]))

        assert plt.get_fignums() == [1, 2]


@pytest.mark.filterwarnings("ignore:No artists with labels:UserWarning")
@pytest.mark.filterwarnings("ignore:Data has no positive values:UserWarning")
class TestCreateTotalReadGraphic:
    STAT = {D(2024, 1, 1): 100, D(2024, 1, 2): 150, D(2024, 1, 3): 1000}

    def test_returns_base64_svg(self):
        svg = decode_svg(trends.create_total_read_graphic(self.STAT))

        assert svg.startswith("<?xml")
        assert "<svg" in svg

    def test_line_is_plotted_on_a_log_scale_with_value_labels(self, axes):
        trends.create_total_read_graphic(self.STAT)

        ax = axes()
        [line] = ax.lines
        assert list(line.get_ydata()) == [100, 150, 1000]
        assert ax.get_yscale() == "log"
        assert [(text.get_position(), text.get_text()) for text in ax.texts] == [
            ((0, 110), "100"),
            ((1, 160), "150"),
            ((2, 1010), "1000"),
        ]
        assert [label.get_text() for label in ax.get_xticklabels()] == [
            "2024-01-01",
            "2024-01-02",
            "2024-01-03",
        ]

    def test_y_axis_ticks_are_formatted_as_integers(self, axes):
        trends.create_total_read_graphic(self.STAT)

        assert axes().yaxis.get_major_formatter()(1000.0, 0) == "1000"

    def test_single_day(self):
        svg = decode_svg(trends.create_total_read_graphic({D(2024, 1, 1): 5}))

        assert "<svg" in svg

    def test_zero_values_on_the_log_scale_are_rendered_current_behaviour(self, axes):
        stat = {D(2024, 1, 1): 0, D(2024, 1, 2): 0}

        svg = decode_svg(trends.create_total_read_graphic(stat))

        assert "<svg" in svg
        assert [text.get_text() for text in axes().texts] == ["0", "0"]

    def test_empty_statistics_are_rendered_current_behaviour(self, axes):
        svg = decode_svg(trends.create_total_read_graphic({}))

        assert "<svg" in svg
        assert list(axes().texts) == []

    def test_legend_has_no_entries_current_behaviour(self, axes):
        with pytest.warns(UserWarning, match="No artists with labels found"):
            trends.create_total_read_graphic(self.STAT)

        assert axes().get_legend().get_texts() == []

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "BUG: tracker/system/trends.py:612 the figure is never closed, so every "
            "rendered graphic stays registered in pyplot (memory leak)"
        ),
    )
    def test_figure_is_closed_after_rendering(self):
        trends.create_total_read_graphic(self.STAT)

        assert plt.get_fignums() == []
