import datetime
from decimal import Decimal

import pytest

from tests.unit.api import factories
from tracker.api.v1 import system as system_api
from tracker.common import database
from tracker.google_drive import db as drive_db, drive_api
from tracker.models import enums
from tracker.reading_log import db as logs_db, statistics
from tracker.system import db as system_db, schemas, trends


BASE = "/api/v1/system"
DAY = datetime.date(2026, 1, 3)
TASK_GROUP_BUG = (
    "BUG: tracker/api/v1/system.py:{line} an error raised inside asyncio.TaskGroup "
    "reaches the app as ExceptionGroup, so the database exception handler is bypassed "
    "and the client gets a bare 500 instead of the JSON error body"
)
SPAN_TRENDS = {
    "get_span_reading_statistics": "reading_trend",
    "get_span_notes_statistics": "notes_trend",
    "get_span_completed_materials_statistics": "completed_materials_trend",
    "get_span_repeated_materials_statistics": "repeated_materials_trend",
    "get_span_outlined_materials_statistics": "outlined_materials_trend",
}
TABLES_STAT = {
    "materials_count": 5,
    "reading_log_count": 40,
    "notes_count": 0,
    "cards_count": 3,
    "repeats_count": 2,
    "note_repeats_history_count": 1,
}


def _span(*amounts: int) -> trends.SpanStatistics:
    first = DAY - datetime.timedelta(days=len(amounts) - 1)
    return trends.SpanStatistics(
        data=[
            trends.DayStatistics(date=first + datetime.timedelta(days=i), amount=amount)
            for i, amount in enumerate(amounts)
        ],
        span_size=len(amounts),
    )


def _tracker_statistics() -> statistics.TrackerStatistics:
    return statistics.TrackerStatistics(
        started_at=DAY,
        finished_at=DAY,
        duration=1,
        lost_time=0,
        mean=1.5,
        median=1.0,
        pages_read={enums.MaterialTypesEnum.book: 2},
        materials_completed={},
        total_materials_completed=0,
        would_be_total=3,
        min_log_record=None,
        max_log_record=None,
    )


@pytest.fixture
def summary(mocker):
    mocks = {
        name: mocker.patch.object(
            trends, name, mocker.AsyncMock(return_value=_span(1, 0, 1))
        )
        for name in SPAN_TRENDS
    }
    mocks["get_tracker_statistics"] = mocker.patch.object(
        statistics,
        "get_tracker_statistics",
        mocker.AsyncMock(return_value=_tracker_statistics()),
    )
    return mocks


async def test_summary(client, summary):
    response = await client.get(f"{BASE}/summary", params={"last_days": 3})

    assert response.status_code == 200
    trend = {
        "total": 2,
        "would_be_total": 3,
        "zero_days": 1,
        "mean": 0.67,
        "median": 1.0,
        "max_record": {"date": "2026-01-01", "amount": 1},
        "min_record": {"date": "2026-01-01", "amount": 1},
    }
    assert response.json() == {
        "tracker_statistics": {
            "started_at": "2026-01-03",
            "finished_at": "2026-01-03",
            "duration": 1,
            "lost_time": 0,
            "mean": 1.5,
            "median": 1.0,
            "pages_read": {"book": 2},
            "materials_completed": {},
            "total_materials_completed": 0,
            "would_be_total": 3,
            "min_log_record": None,
            "max_log_record": None,
            "duration_period": "1 days",
            "total_pages_read": 2,
            "lost_time_period": "",
            "lost_time_percent": 0.0,
            "would_be_total_percent": 150.0,
        },
        **dict.fromkeys(SPAN_TRENDS.values(), trend),
    }
    summary["get_tracker_statistics"].assert_awaited_once_with()
    for name in SPAN_TRENDS:
        summary[name].assert_awaited_once_with(span_size=3)


async def test_summary_of_an_empty_reading_log_has_no_tracker_statistics(client, summary):
    summary["get_tracker_statistics"].return_value = None

    response = await client.get(f"{BASE}/summary", params={"last_days": 3})

    assert response.status_code == 200
    assert response.json()["tracker_statistics"] is None


async def test_summary_of_an_all_zero_span(client, summary):
    for name in SPAN_TRENDS:
        summary[name].return_value = _span(0)

    response = await client.get(f"{BASE}/summary", params={"last_days": 1})

    assert response.status_code == 200
    assert response.json()["notes_trend"] == {
        "total": 0,
        "would_be_total": 0,
        "zero_days": 1,
        "mean": 0.0,
        "median": 0.0,
        "max_record": {"date": "2026-01-03", "amount": 0},
        "min_record": {"date": "2026-01-03", "amount": 0},
    }


LAST_DAYS_ENDPOINTS = [
    "summary",
    "graphics/reading-trend",
    "graphics/notes-trend",
    "graphics/completed-materials-trend",
    "graphics/repeated-materials-trend",
    "graphics/outlined-materials-trend",
    "graphics/total-read",
]


@pytest.mark.parametrize("path", LAST_DAYS_ENDPOINTS)
@pytest.mark.parametrize(
    "params",
    [{}, {"last_days": 0}, {"last_days": -1}, {"last_days": "week"}, {"last_days": 1.5}],
    ids=["missing", "zero", "negative", "not-int", "fractional"],
)
async def test_last_days_must_be_a_positive_integer(client, path, params):
    response = await client.get(f"{BASE}/{path}", params=params)

    assert response.status_code == 422
    assert response.json()["detail"].startswith("query.last_days: ")


@pytest.mark.xfail(strict=True, reason=TASK_GROUP_BUG.format(line=25))
async def test_summary_reports_a_database_failure_as_json(lenient_client, summary):
    summary["get_span_notes_statistics"].side_effect = trends.TrendException(
        "Wrong span size"
    )

    response = await lenient_client.get(f"{BASE}/summary", params={"last_days": 3})

    assert response.status_code == 500
    assert response.text == '{"detail":"Database error: Wrong span size"}'


async def test_reading_progress_graphic(client, mocker):
    create = mocker.patch.object(
        system_db, "create_reading_graphic", mocker.AsyncMock(return_value="aW1hZ2U=")
    )

    response = await client.get(
        f"{BASE}/graphics/reading-progress",
        params={"material_id": str(factories.MATERIAL_ID), "last_days": 7},
    )

    assert response.status_code == 200
    assert response.json() == {"image": "aW1hZ2U="}
    create.assert_awaited_once_with(material_id=factories.MATERIAL_ID, last_days=7)


@pytest.mark.parametrize(
    ("params", "location"),
    [
        ({"last_days": 7}, "query.material_id"),
        ({"material_id": "x", "last_days": 7}, "query.material_id"),
        ({"material_id": str(factories.MATERIAL_ID)}, "query.last_days"),
        ({"material_id": str(factories.MATERIAL_ID), "last_days": 0}, "query.last_days"),
    ],
    ids=["no-material", "bad-uuid", "no-last-days", "zero-last-days"],
)
async def test_reading_progress_graphic_rejects_invalid_query(
    client, mocker, params, location
):
    create = mocker.patch.object(system_db, "create_reading_graphic", mocker.AsyncMock())

    response = await client.get(f"{BASE}/graphics/reading-progress", params=params)

    assert response.status_code == 422
    assert response.json()["detail"].startswith(f"{location}: ")
    create.assert_not_awaited()


async def test_reading_progress_graphic_of_a_missing_material_is_404(client, mocker):
    mocker.patch.object(
        system_db,
        "create_reading_graphic",
        mocker.AsyncMock(side_effect=database.NotFoundException("Material not found")),
    )

    response = await client.get(
        f"{BASE}/graphics/reading-progress",
        params={"material_id": str(factories.MATERIAL_ID), "last_days": 7},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "NotFoundError: Material not found"}


async def test_outline_percentage_graphic(client, mocker):
    create = mocker.patch.object(
        system_db,
        "create_outline_percentage_graphic",
        mocker.AsyncMock(return_value="aW1hZ2U="),
    )

    response = await client.get(f"{BASE}/graphics/outline-percentage")

    assert response.status_code == 200
    assert response.json() == {"image": "aW1hZ2U="}
    create.assert_awaited_once_with()


@pytest.fixture
def reading_trend(mocker):
    stat = _span(4, 5)
    completion_dates = {factories.MATERIAL_ID: datetime.datetime(2026, 1, 2, 10, 0)}
    return {
        "stat": stat,
        "completion_dates": completion_dates,
        "get_stat": mocker.patch.object(
            trends, "get_span_reading_statistics", mocker.AsyncMock(return_value=stat)
        ),
        "get_dates": mocker.patch.object(
            logs_db,
            "get_completion_dates",
            mocker.AsyncMock(return_value=completion_dates),
        ),
        "create": mocker.patch.object(
            trends, "create_reading_graphic", mocker.Mock(return_value="aW1hZ2U=")
        ),
    }


async def test_reading_trend_graphic(client, reading_trend):
    response = await client.get(f"{BASE}/graphics/reading-trend", params={"last_days": 2})

    assert response.status_code == 200
    assert response.json() == {"image": "aW1hZ2U="}
    reading_trend["get_stat"].assert_awaited_once_with(span_size=2)
    reading_trend["get_dates"].assert_awaited_once_with()
    reading_trend["create"].assert_called_once_with(
        reading_trend["stat"], completion_dates=reading_trend["completion_dates"]
    )


@pytest.mark.xfail(strict=True, reason=TASK_GROUP_BUG.format(line=76))
async def test_reading_trend_graphic_reports_a_database_failure_as_json(
    lenient_client, reading_trend
):
    reading_trend["get_dates"].side_effect = database.DatabaseException("connection lost")

    response = await lenient_client.get(
        f"{BASE}/graphics/reading-trend", params={"last_days": 2}
    )

    assert response.status_code == 500
    assert response.text == '{"detail":"Database error: connection lost"}'
    reading_trend["create"].assert_not_called()


@pytest.mark.parametrize(
    ("path", "get_statistics", "create_graphic"),
    [
        ("notes-trend", "get_span_notes_statistics", "create_notes_graphic"),
        (
            "completed-materials-trend",
            "get_span_completed_materials_statistics",
            "create_completed_materials_graphic",
        ),
        (
            "repeated-materials-trend",
            "get_span_repeated_materials_statistics",
            "create_repeated_materials_graphic",
        ),
        (
            "outlined-materials-trend",
            "get_span_outlined_materials_statistics",
            "create_outlined_materials_graphic",
        ),
        ("total-read", "get_span_total_read_statistics", "create_total_read_graphic"),
    ],
)
class TestTrendGraphic:
    async def test_draws_the_span_statistics(
        self, client, mocker, path, get_statistics, create_graphic
    ):
        stat = _span(1, 2, 3)
        get_stat = mocker.patch.object(
            trends, get_statistics, mocker.AsyncMock(return_value=stat)
        )
        create = mocker.patch.object(
            trends, create_graphic, mocker.Mock(return_value="aW1hZ2U=")
        )

        response = await client.get(f"{BASE}/graphics/{path}", params={"last_days": 3})

        assert response.status_code == 200
        assert response.json() == {"image": "aW1hZ2U="}
        get_stat.assert_awaited_once_with(span_size=3)
        create.assert_called_once_with(stat)

    async def test_reports_a_trend_failure(
        self, client, mocker, path, get_statistics, create_graphic
    ):
        mocker.patch.object(
            trends,
            get_statistics,
            mocker.AsyncMock(side_effect=trends.TrendException("Wrong span size")),
        )
        create = mocker.patch.object(trends, create_graphic, mocker.Mock())

        response = await client.get(f"{BASE}/graphics/{path}", params={"last_days": 3})

        assert response.status_code == 500
        assert response.json() == {"detail": "Database error: Wrong span size"}
        create.assert_not_called()


def test_tables_stat_keeps_only_the_known_counters():
    assert system_api._tables_stat({**TABLES_STAT, "statuses_count": 9}) == TABLES_STAT


@pytest.mark.parametrize("missing", sorted(TABLES_STAT))
def test_tables_stat_fails_on_a_missing_counter_current_behaviour(missing):
    stat = {key: value for key, value in TABLES_STAT.items() if key != missing}

    with pytest.raises(KeyError, match=missing):
        system_api._tables_stat(stat)


def test_tables_stat_matches_the_tables_the_analytics_counts():
    assert {f"{table}_count" for table in drive_db.TABLES} == TABLES_STAT.keys()


@pytest.fixture
def drive(mocker):
    calls = mocker.Mock()
    mocks = {
        "backup": mocker.patch.object(
            drive_api, "backup", mocker.AsyncMock(return_value="dump.json")
        ),
        "restore": mocker.patch.object(drive_api, "restore", mocker.AsyncMock()),
        "analytics": mocker.patch.object(
            drive_db, "get_tables_analytics", mocker.AsyncMock(return_value=TABLES_STAT)
        ),
    }
    for name, mock in mocks.items():
        calls.attach_mock(mock, name)
    return {**mocks, "calls": calls}


async def test_backup(client, drive):
    response = await client.post(f"{BASE}/backup")

    assert response.status_code == 200
    assert response.json() == TABLES_STAT
    drive["backup"].assert_awaited_once_with()
    drive["analytics"].assert_awaited_once_with()
    drive["restore"].assert_not_awaited()


@pytest.mark.xfail(strict=True, reason=TASK_GROUP_BUG.format(line=148))
async def test_backup_reports_a_database_failure_as_json(lenient_client, drive):
    drive["analytics"].side_effect = database.DatabaseException("connection lost")

    response = await lenient_client.post(f"{BASE}/backup")

    assert response.status_code == 500
    assert response.text == '{"detail":"Database error: connection lost"}'


async def test_backup_service_failure_is_500_current_behaviour(lenient_client, drive):
    drive["backup"].side_effect = drive_api.GoogleDriveException("no quota")

    response = await lenient_client.post(f"{BASE}/backup")

    assert response.status_code == 500
    assert response.text == "Internal Server Error"


async def test_restore_counts_the_rows_after_restoring(client, drive, mocker):
    response = await client.post(f"{BASE}/restore")

    assert response.status_code == 200
    assert response.json() == TABLES_STAT
    assert drive["calls"].mock_calls == [mocker.call.restore(), mocker.call.analytics()]


async def test_restore_failure_does_not_count_rows(lenient_client, drive):
    drive["restore"].side_effect = drive_api.GoogleDriveException("no dump")

    response = await lenient_client.post(f"{BASE}/restore")

    assert response.status_code == 500
    drive["analytics"].assert_not_awaited()


@pytest.mark.parametrize("endpoint", ["backup", "restore"])
async def test_negative_counter_is_a_server_error(lenient_client, drive, endpoint):
    drive["analytics"].return_value = {**TABLES_STAT, "notes_count": -1}

    response = await lenient_client.post(f"{BASE}/{endpoint}")

    assert response.status_code == 500


@pytest.fixture
def get_span_analytics(mocker):
    analysis = trends.SpanAnalysis(
        reading=_span(10, 0, 20),
        notes=_span(0, 0, 0),
        materials_analytics=trends._MaterialAnalytics(
            stats={enums.MaterialTypesEnum.book: 1, enums.MaterialTypesEnum.article: 2},
            total=3,
        ),
        reading_analytics=trends._MaterialAnalytics(
            stats={enums.MaterialTypesEnum.book: 30}, total=30
        ),
        repeat_analytics=trends._RepeatAnalytics(
            repeats_count=4, unique_materials_count=2
        ),
    )
    return mocker.patch.object(
        trends, "get_span_analytics", mocker.AsyncMock(return_value=analysis)
    )


async def test_report(client, get_span_analytics):
    response = await client.post(
        f"{BASE}/report", json={"start": "2026-01-01", "stop": "2026-01-03"}
    )

    assert response.status_code == 200
    assert response.json() == {
        "completed_materials": {"book": 1, "article": 2},
        "total_materials_completed": 3,
        "read_items": {"book": 30},
        "reading": {
            "total": 30,
            "median": 10.0,
            "mean": 10.0,
            "lost_count": 10,
            "zero_days": 1,
            "would_be_total": 40,
        },
        "notes": {
            "total": 0,
            "median": 0.0,
            "mean": 0.0,
            "lost_count": 0,
            "zero_days": 3,
            "would_be_total": 0,
        },
        "repeats_total": 4,
        "repeat_materials_count": 2,
    }
    get_span_analytics.assert_awaited_once_with(
        schemas.GetSpanReportRequest(
            start=datetime.date(2026, 1, 1), stop=datetime.date(2026, 1, 3)
        ),
    )
    assert isinstance(get_span_analytics.return_value.reading.mean, Decimal)


async def test_report_accepts_a_two_day_span(client, get_span_analytics):
    response = await client.post(
        f"{BASE}/report", json={"start": "2026-01-01", "stop": "2026-01-02"}
    )

    assert response.status_code == 200
    assert get_span_analytics.await_args.args[0].size == 2


@pytest.mark.parametrize(
    ("body", "detail"),
    [
        (
            {"start": "2026-01-02", "stop": "2026-01-01"},
            "body.stop: Value error, Start must not be after stop",
        ),
        ({"start": "garbage"}, "body.start: Input should be a valid date"),
        (
            {"start": "2026-01-01", "stop": "garbage"},
            "body.stop: Input should be a valid date",
        ),
        (
            {"start": "2026-01-01", "stop": "2026-01-03", "size": 3},
            "body.size: Extra inputs are not permitted",
        ),
        ({"start": None, "stop": None}, "body.start: Input should be a valid date"),
    ],
    ids=["stop-before-start", "bad-start", "bad-stop", "extra", "nulls"],
)
async def test_report_rejects_invalid_body(client, get_span_analytics, body, detail):
    response = await client.post(f"{BASE}/report", json=body)

    assert response.status_code == 422
    assert response.json()["detail"].startswith(detail)
    get_span_analytics.assert_not_awaited()


async def test_report_accepts_a_one_day_span(client, get_span_analytics):
    response = await client.post(
        f"{BASE}/report", json={"start": "2026-01-01", "stop": "2026-01-01"}
    )

    assert response.status_code == 200
    assert get_span_analytics.await_args.args[0].size == 1


@pytest.mark.parametrize(
    "body",
    [{"stop": "2026-01-03"}, {"start": "garbage", "stop": "2026-01-03"}],
    ids=["start-missing", "start-invalid"],
)
async def test_report_rejects_a_stop_without_a_valid_start(
    lenient_client, get_span_analytics, body
):
    response = await lenient_client.post(f"{BASE}/report", json=body)

    assert response.status_code == 422
    assert response.json()["detail"].startswith("body.start: ")
