import datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from tests.unit.materials.helpers import NOW, midnight, uid
from tracker.common import database
from tracker.materials import db
from tracker.models import enums


@pytest.mark.parametrize(
    ("duration", "expected"),
    [
        (0, ""),
        (1, "1 days"),
        (29, "29 days"),
        (30, "1 months"),
        (31, "1 months, 1 days"),
        (65, "2 months, 5 days"),
        (360, "12 months"),
        (364, "12 months, 4 days"),
        (365, "1 years"),
        (366, "1 years, 1 days"),
        (380, "1 years, 15 days"),
        (395, "1 years, 1 months"),
        (730, "2 years"),
        (790, "2 years, 2 months"),
        (792, "2 years, 2 months, 2 days"),
        (706, "1 years, 11 months, 11 days"),
    ],
    ids=lambda value: f"{value!r}",
)
def test_convert_duration_to_period_from_days(duration, expected):
    assert db._convert_duration_to_period(duration) == expected


@pytest.mark.parametrize(
    ("duration", "expected"),
    [
        (datetime.timedelta(0), ""),
        (datetime.timedelta(hours=23, minutes=59), ""),
        (datetime.timedelta(days=1), "1 days"),
        (datetime.timedelta(days=1, hours=23), "1 days"),
        (datetime.timedelta(days=30), "1 months"),
        (datetime.timedelta(days=365), "1 years"),
        (datetime.timedelta(days=792), "2 years, 2 months, 2 days"),
    ],
    ids=["zero", "less-than-a-day", "one-day", "partial-day-dropped", "month", "year", "all"],
)
def test_convert_duration_to_period_from_timedelta(duration, expected):
    assert db._convert_duration_to_period(duration) == expected


@pytest.mark.parametrize(
    ("started_at", "completed_at", "expected"),
    [
        (midnight(0), midnight(0), "1 days"),
        (midnight(-6), midnight(0), "7 days"),
        (midnight(-29), midnight(0), "1 months"),
        (midnight(-30), midnight(0), "1 months, 1 days"),
        (midnight(-364), midnight(0), "1 years"),
    ],
    ids=["same-day", "week", "month-boundary", "month-and-day", "year-boundary"],
)
def test_total_reading_duration_of_completed_material_includes_both_ends(
    started_at,
    completed_at,
    expected,
):
    result = db._get_total_reading_duration(
        started_at=started_at,
        completed_at=completed_at,
    )

    assert result == expected


@pytest.mark.parametrize(
    ("started_at", "expected"),
    [
        (midnight(0), "1 days"),
        (midnight(-6), "7 days"),
        (midnight(-30), "1 months, 1 days"),
    ],
    ids=["started-today", "week-ago", "month-ago"],
)
def test_total_reading_duration_of_reading_material_counts_up_to_now(
    frozen_now,
    started_at,
    expected,
):
    result = db._get_total_reading_duration(started_at=started_at, completed_at=None)

    assert result == expected


def test_total_reading_duration_ignores_completion_when_clock_is_not_needed(mocker):
    utcnow = mocker.patch.object(database, "utcnow")

    db._get_total_reading_duration(started_at=midnight(-1), completed_at=midnight(0))

    utcnow.assert_not_called()


@pytest.mark.parametrize(
    ("priority_days", "repeats_count", "expected"),
    [
        (None, 0, 0),
        (0, 0, 0),
        (0, 3, 0),
        (2, 0, 2 / 30),
        (29, 0, 29 / 30),
        (30, 0, 1.0),
        (45, 0, 1.5),
        (92, 0, 92 / 30),
        (2, 2, 0),
        (29, 1, 0),
        (30, 1, 0.0),
        (31, 1, 1 / 30),
        (59, 2, 0),
        (80, 2, 20 / 30),
        (102, 2, 1.4),
        (180, 3, 3.0),
        (-5, 0, 0),
    ],
    ids=lambda value: f"{value!r}",
)
def test_calculate_priority_months(priority_days, repeats_count, expected):
    result = db._calculate_priority_months(priority_days, repeats_count=repeats_count)

    assert result == pytest.approx(expected)


@pytest.mark.parametrize(
    ("priority_days", "repeats_count", "expected_days", "expected_months"),
    [
        (None, 0, 0, 0),
        (None, 5, 0, 0),
        (0, 0, 0, 0),
        (60, 1, 60, 1.0),
        (45, 0, 45, 1.5),
        (59, 2, 59, 0),
    ],
    ids=["none", "none-with-repeats", "zero", "one-repeat", "no-repeats", "below-limit"],
)
def test_repeat_analytics_priority_months(
    priority_days,
    repeats_count,
    expected_days,
    expected_months,
):
    analytics = db.RepeatAnalytics(
        repeats_count=repeats_count,
        last_repeated_at=None,
        priority_days=priority_days,
    )

    assert analytics.priority_days == expected_days
    assert analytics.priority_months == pytest.approx(expected_months)
    assert analytics.model_dump()["priority_months"] == pytest.approx(expected_months)


def test_repeat_analytics_is_built_from_row_attributes():
    row = SimpleNamespace(
        material_id=uid(1),
        repeats_count=2,
        last_repeated_at=NOW,
        priority_days=90,
    )

    with pytest.raises(ValidationError, match="material_id"):
        db.RepeatAnalytics.model_validate(vars(row))

    analytics = db.RepeatAnalytics.model_validate(row, from_attributes=True)
    assert analytics.repeats_count == 2
    assert analytics.last_repeated_at == NOW
    assert analytics.priority_months == pytest.approx(1.0)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, 0),
        (datetime.timedelta(days=0), 0),
        (datetime.timedelta(days=29), 29),
        (datetime.timedelta(days=92, hours=23), 92),
        (datetime.timedelta(days=-3), -3),
    ],
    ids=["none", "zero", "days", "partial-day-dropped", "negative"],
)
def test_get_priority_days(value, expected):
    assert db._get_priority_days(value) == expected


@pytest.mark.parametrize(
    "start_date",
    [datetime.date(2024, 2, 29), datetime.date(1999, 12, 31)],
    ids=["leap-day", "old-date"],
)
def test_token_start_date_parses_iso_date(start_date):
    assert db._token_start_date({"start_date": start_date.isoformat()}) == start_date


@pytest.mark.parametrize(
    "continue_from",
    [
        {},
        {"cursor": "abc"},
        {"start_date": ""},
        {"start_date": "2023-02-29"},
        {"start_date": "10.03.2024"},
        {"start_date": "tomorrow"},
    ],
    ids=["empty", "missing-key", "empty-date", "not-a-leap-year", "wrong-format", "garbage"],
)
def test_token_start_date_rejects_invalid_token(continue_from):
    with pytest.raises(
        database.InvalidNextTokenException,
        match="^next_token has no valid start date$",
    ):
        db._token_start_date(continue_from)


def _queue_row(**overrides):
    fields = {
        "material_id": uid(7),
        "title": "Мастер и Маргарита",
        "pages": 480,
        "material_type": "book",
        "is_outlined": True,
        "completed_at": midnight(-100),
        "notes_count": 12,
        "cards_count": 3,
        "repeats_count": 1,
        "last_repeated_at": midnight(-75),
        "priority_days": 75,
    }
    return SimpleNamespace(**(fields | overrides))


def test_to_repeating_queue_copies_row_and_calculates_priority_months():
    item = db._to_repeating_queue(_queue_row())

    assert item == db.RepeatingQueue(
        material_id=uid(7),
        title="Мастер и Маргарита",
        pages=480,
        material_type=enums.MaterialTypesEnum.book,
        is_outlined=True,
        completed_at=midnight(-100),
        notes_count=12,
        cards_count=3,
        repeats_count=1,
        last_repeated_at=midnight(-75),
        priority_days=75,
        priority_months=1.5,
    )


def test_to_repeating_queue_of_never_repeated_material():
    item = db._to_repeating_queue(
        _queue_row(repeats_count=0, last_repeated_at=None, priority_days=30),
    )

    assert item.last_repeated_at is None
    assert item.priority_months == 1.0
