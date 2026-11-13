import datetime
from contextlib import asynccontextmanager
from uuid import UUID

import pytest
import sqlalchemy.exc
from sqlalchemy.dialects import postgresql

from tests.unit.system.conftest import build_statistics
from tracker.common import database
from tracker.models import enums
from tracker.reading_log import db as logs_db
from tracker.system import schemas, trends


D = datetime.date
TODAY = D(2024, 1, 7)
WEEK = trends.TimeSpan(start=D(2024, 1, 1), stop=TODAY, span_size=7)


@pytest.fixture
def frozen_clock(mocker):
    mocker.patch.object(
        database,
        "utcnow",
        return_value=datetime.datetime(2024, 1, 7, 12, 0, 0),  # noqa: DTZ001
    )


SPAN_STATISTICS = [
    (trends.get_span_reading_statistics, "_calculate_span_reading_statistics"),
    (trends.get_span_notes_statistics, "_calculate_span_notes_statistics"),
    (
        trends.get_span_completed_materials_statistics,
        "_calculate_span_completed_materials_statistics",
    ),
    (
        trends.get_span_repeated_materials_statistics,
        "_calculate_span_repeated_materials_statistics",
    ),
    (
        trends.get_span_outlined_materials_statistics,
        "_calculate_span_outlined_materials_statistics",
    ),
]


@pytest.mark.usefixtures("frozen_clock")
@pytest.mark.parametrize(
    ("get_statistics", "calculate_name"),
    SPAN_STATISTICS,
    ids=[name for _, name in SPAN_STATISTICS],
)
class TestGetSpanStatisticsWrappers:
    async def test_statistics_cover_the_span_ending_today(
        self,
        mocker,
        get_statistics,
        calculate_name,
    ):
        calculate = mocker.patch.object(
            trends,
            calculate_name,
            mocker.AsyncMock(return_value={D(2024, 1, 1): 3, TODAY: 4}),
        )

        result = await get_statistics(span_size=7)

        assert result == build_statistics([3, 0, 0, 0, 0, 0, 4])
        calculate.assert_awaited_once_with(span=WEEK)

    async def test_one_day_span_is_today(self, mocker, get_statistics, calculate_name):
        calculate = mocker.patch.object(
            trends,
            calculate_name,
            mocker.AsyncMock(return_value={}),
        )

        result = await get_statistics(span_size=1)

        assert result == build_statistics([0], start=TODAY)
        calculate.assert_awaited_once_with(
            span=trends.TimeSpan(start=TODAY, stop=TODAY, span_size=1),
        )

    async def test_zero_span_size_is_rejected_before_any_query(
        self,
        mocker,
        get_statistics,
        calculate_name,
    ):
        calculate = mocker.patch.object(trends, calculate_name, mocker.AsyncMock())

        with pytest.raises(trends.TrendException):
            await get_statistics(span_size=0)

        calculate.assert_not_awaited()


@pytest.mark.usefixtures("frozen_clock")
async def test_get_span_total_read_statistics_passes_the_span(mocker):
    total_read = {TODAY: 10}
    calculate = mocker.patch.object(
        trends,
        "_calculate_span_total_read",
        mocker.AsyncMock(return_value=total_read),
    )

    result = await trends.get_span_total_read_statistics(span_size=7)

    assert result is total_read
    calculate.assert_awaited_once_with(span=WEEK)


class TestCalculateSpanTotalRead:
    SPAN = trends.TimeSpan(start=D(2024, 1, 2), stop=D(2024, 1, 5), span_size=4)

    @pytest.fixture
    def logs(self, mocker):
        def install(records: list[tuple[datetime.date, int]], *, sum_before: int):
            list_records = mocker.patch.object(
                logs_db,
                "list_log_records",
                mocker.AsyncMock(
                    return_value=[
                        logs_db.LogRecord(date=date, count=count, material_id=UUID(int=1))
                        for date, count in records
                    ],
                ),
            )
            records_sum = mocker.patch.object(
                logs_db,
                "records_sum",
                mocker.AsyncMock(return_value=sum_before),
            )
            return list_records, records_sum

        return install

    async def test_running_sum_starts_from_pages_read_before_the_span(self, logs):
        list_records, records_sum = logs(
            [(D(2024, 1, 2), 10), (D(2024, 1, 4), 5)],
            sum_before=100,
        )

        result = await trends._calculate_span_total_read(span=self.SPAN)

        assert result == {
            D(2024, 1, 2): 110,
            D(2024, 1, 3): 110,
            D(2024, 1, 4): 115,
            D(2024, 1, 5): 115,
        }
        list_records.assert_awaited_once_with(from_date=D(2024, 1, 2), to_date=D(2024, 1, 5))
        records_sum.assert_awaited_once_with(to_date=D(2024, 1, 1))

    async def test_records_of_one_day_are_summed(self, logs):
        logs([(D(2024, 1, 3), 1), (D(2024, 1, 3), 2), (D(2024, 1, 3), 3)], sum_before=0)

        result = await trends._calculate_span_total_read(span=self.SPAN)

        assert list(result.values()) == [0, 6, 6, 6]

    async def test_no_records_keep_the_sum_before(self, logs):
        logs([], sum_before=42)

        result = await trends._calculate_span_total_read(span=self.SPAN)

        assert result == dict.fromkeys(self.SPAN.iter(), 42)

    async def test_nothing_read_at_all_gives_zeros(self, logs):
        logs([], sum_before=0)

        result = await trends._calculate_span_total_read(span=self.SPAN)

        assert list(result.values()) == [0, 0, 0, 0]

    async def test_records_outside_the_span_are_ignored(self, logs):
        logs([(D(2024, 1, 1), 50), (D(2024, 1, 6), 50), (D(2024, 1, 5), 1)], sum_before=0)

        result = await trends._calculate_span_total_read(span=self.SPAN)

        assert list(result.values()) == [0, 0, 0, 1]

    async def test_one_day_span(self, logs):
        logs([(D(2024, 1, 2), 3)], sum_before=7)
        span = trends.TimeSpan(start=D(2024, 1, 2), stop=D(2024, 1, 2), span_size=1)

        assert await trends._calculate_span_total_read(span=span) == {D(2024, 1, 2): 10}


class TestGetSpanAnalytics:
    REQUEST = schemas.GetSpanReportRequest(start=D(2024, 1, 1), stop=D(2024, 1, 3))
    SPAN = trends.TimeSpan(start=D(2024, 1, 1), stop=D(2024, 1, 3), span_size=3)

    @pytest.fixture
    def queries(self, mocker):
        materials = trends._MaterialAnalytics(
            stats={enums.MaterialTypesEnum.book: 2},
            total=2,
        )
        reading = trends._MaterialAnalytics(
            stats={enums.MaterialTypesEnum.book: 30, enums.MaterialTypesEnum.article: 5},
            total=35,
        )
        repeats = trends._RepeatAnalytics(repeats_count=4, unique_materials_count=3)
        returns = {
            "_calculate_span_reading_statistics": {D(2024, 1, 1): 30, D(2024, 1, 3): 5},
            "_calculate_span_notes_statistics": {D(2024, 1, 2): 6},
            "_materials_analytics": materials,
            "_reading_analytics": reading,
            "_get_repeats_count": repeats,
        }
        return {
            name: mocker.patch.object(trends, name, mocker.AsyncMock(return_value=value))
            for name, value in returns.items()
        }

    async def test_analysis_combines_every_query(self, queries):
        result = await trends.get_span_analytics(self.REQUEST)

        assert result.reading == build_statistics([30, 0, 5])
        assert result.notes == build_statistics([0, 6, 0])
        assert result.materials_analytics.model_dump() == {"stats": {"book": 2}, "total": 2}
        assert result.reading_analytics.model_dump() == {
            "stats": {"book": 30, "article": 5},
            "total": 35,
        }
        assert result.repeat_analytics.model_dump() == {
            "repeats_count": 4,
            "unique_materials_count": 3,
        }

    async def test_every_query_gets_the_requested_span(self, queries):
        await trends.get_span_analytics(self.REQUEST)

        for query in queries.values():
            query.assert_awaited_once_with(self.SPAN)

    async def test_empty_span_data_gives_zero_statistics(self, mocker, queries):
        queries["_calculate_span_reading_statistics"].return_value = {}
        queries["_calculate_span_notes_statistics"].return_value = {}

        result = await trends.get_span_analytics(self.REQUEST)

        assert result.reading == build_statistics([0, 0, 0])
        assert result.notes == build_statistics([0, 0, 0])

    async def test_failed_query_is_raised_as_an_exception_group(self, queries):
        queries["_get_repeats_count"].side_effect = trends.TrendException("boom")

        with pytest.raises(ExceptionGroup) as e:
            await trends.get_span_analytics(self.REQUEST)

        assert [str(error) for error in e.value.exceptions] == ["boom"]


class CompilingSession:
    """Compiles statements for PostgreSQL the way a real execute() would."""

    def __init__(self, rows: list) -> None:
        self._rows = rows
        self.sql: list[str] = []

    async def execute(self, stmt):
        self.sql.append(str(stmt.compile(dialect=postgresql.dialect())))
        return self

    def all(self) -> list:
        return self._rows


@pytest.mark.xfail(
    strict=True,
    raises=sqlalchemy.exc.InvalidRequestError,
    reason=(
        "BUG: tracker/system/trends.py:472 .join(models.ReadingLog) has no ON clause "
        "and the tables define no foreign key, so the statement cannot be compiled "
        "and the span report always fails"
    ),
)
async def test_reading_analytics_groups_read_pages_by_material_type(mocker):
    session = CompilingSession(
        [mocker.Mock(material_type=enums.MaterialTypesEnum.book, cnt=30)],
    )

    @asynccontextmanager
    async def open_session(**_kwargs):
        yield session

    mocker.patch.object(database, "session", open_session)
    span = trends.TimeSpan(start=D(2024, 1, 1), stop=D(2024, 1, 3), span_size=3)

    result = await trends._reading_analytics(span)

    assert "JOIN reading_log ON" in session.sql[0]
    assert result == trends._MaterialAnalytics(
        stats={enums.MaterialTypesEnum.book: 30},
        total=30,
    )


class TestGetRepeatsCount:
    SPAN = trends.TimeSpan(start=D(2024, 1, 1), stop=D(2024, 1, 3), span_size=3)

    @pytest.fixture
    def aggregate_row(self, mocker):
        def install(row):
            result = mocker.Mock()
            result.mappings.return_value.one_or_none.return_value = row
            session = mocker.Mock(execute=mocker.AsyncMock(return_value=result))

            @asynccontextmanager
            async def open_session(**_kwargs):
                yield session

            mocker.patch.object(database, "session", open_session)

        return install

    async def test_counts_are_read_from_the_aggregate_row(self, mocker, aggregate_row):
        aggregate_row(mocker.Mock(cnt=5, ucnt=2))

        result = await trends._get_repeats_count(self.SPAN)

        assert result == trends._RepeatAnalytics(repeats_count=5, unique_materials_count=2)

    # an aggregate query always returns a row, so only a fake can reach this branch
    async def test_missing_aggregate_row_gives_zeros(self, aggregate_row):
        aggregate_row(None)

        result = await trends._get_repeats_count(self.SPAN)

        assert result == trends._RepeatAnalytics(repeats_count=0, unique_materials_count=0)
