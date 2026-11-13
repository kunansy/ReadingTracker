import datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from tests.unit.system.conftest import frozen_datetime_module
from tracker.system import schemas


START = datetime.date(2024, 1, 10)
NOW = datetime.datetime(2024, 3, 5, 23, 59, 59)  # noqa: DTZ001


@pytest.fixture
def frozen_now(mocker):
    mocker.patch.object(schemas, "datetime", frozen_datetime_module(NOW))


class TestGetSpanReportRequest:
    def test_now_is_the_utc_date(self, frozen_now):
        assert schemas._now() == datetime.date(2024, 3, 5)

    def test_stop_defaults_to_today(self, frozen_now):
        request = schemas.GetSpanReportRequest(start=START)

        assert request.stop == datetime.date(2024, 3, 5)
        assert request.size == 56

    def test_explicit_stop_is_kept(self):
        request = schemas.GetSpanReportRequest(start=START, stop=datetime.date(2024, 1, 12))

        assert request.stop == datetime.date(2024, 1, 12)

    @pytest.mark.parametrize(
        ("stop", "size"),
        [
            (datetime.date(2024, 1, 11), 2),
            (datetime.date(2024, 1, 16), 7),
            (datetime.date(2024, 2, 10), 32),
            (datetime.date(2025, 1, 9), 366),
        ],
        ids=["two-days", "week", "over-month-border", "leap-year"],
    )
    def test_size_includes_both_borders(self, stop, size):
        assert schemas.GetSpanReportRequest(start=START, stop=stop).size == size

    def test_strings_are_parsed(self):
        request = schemas.GetSpanReportRequest(start="2024-01-10", stop="2024-01-11")

        assert (request.start, request.stop) == (START, datetime.date(2024, 1, 11))

    def test_stop_before_start_is_rejected(self):
        with pytest.raises(ValidationError, match="Start must be less than stop"):
            schemas.GetSpanReportRequest(start=START, stop=datetime.date(2024, 1, 9))

    def test_one_day_span_is_rejected_current_behaviour(self):
        with pytest.raises(ValidationError, match="Start must be less than stop"):
            schemas.GetSpanReportRequest(start=START, stop=START)

    def test_default_stop_is_not_validated_against_start_current_behaviour(
        self,
        frozen_now,
    ):
        request = schemas.GetSpanReportRequest(start=datetime.date(2024, 3, 6))

        assert request.size == 0

    @pytest.mark.xfail(
        strict=True,
        raises=KeyError,
        reason=(
            "BUG: tracker/system/schemas.py:26 info.data['start'] raises KeyError "
            "when start itself failed validation, instead of a ValidationError"
        ),
    )
    @pytest.mark.parametrize("start", ["garbage", None, "2024-13-01"])
    def test_invalid_start_is_a_validation_error(self, start):
        with pytest.raises(ValidationError, match="start"):
            schemas.GetSpanReportRequest(start=start, stop=datetime.date(2024, 1, 12))

    @pytest.mark.xfail(
        strict=True,
        raises=KeyError,
        reason=(
            "BUG: tracker/system/schemas.py:26 info.data['start'] raises KeyError "
            "when start is missing, instead of a ValidationError"
        ),
    )
    def test_missing_start_is_a_validation_error(self):
        with pytest.raises(ValidationError, match="start"):
            schemas.GetSpanReportRequest(stop=datetime.date(2024, 1, 12))

    def test_invalid_stop_is_rejected(self):
        with pytest.raises(ValidationError, match="stop"):
            schemas.GetSpanReportRequest(start=START, stop="garbage")

    @pytest.mark.parametrize("ago", [1, 7, 365])
    def test_create_span_ago_shifts_both_borders(self, ago):
        request = schemas.GetSpanReportRequest(start=START, stop=datetime.date(2024, 1, 16))

        shifted = request.create_span_ago(ago)

        assert shifted.start == START - datetime.timedelta(days=ago)
        assert shifted.stop == datetime.date(2024, 1, 16) - datetime.timedelta(days=ago)
        assert shifted.size == request.size

    def test_create_span_ago_leaves_the_original_untouched(self):
        request = schemas.GetSpanReportRequest(start=START, stop=datetime.date(2024, 1, 16))

        request.create_span_ago(3)

        assert (request.start, request.stop) == (START, datetime.date(2024, 1, 16))

    @pytest.mark.parametrize("ago", [0, -1, -100])
    def test_create_span_ago_rejects_non_positive_shift(self, ago):
        request = schemas.GetSpanReportRequest(start=START, stop=datetime.date(2024, 1, 16))

        with pytest.raises(ValueError, match=f"Ago must be > 0, {ago} found"):
            request.create_span_ago(ago)


LAST_DAYS_REQUESTS = [
    schemas.GetSystemSummaryRequest,
    schemas.GetReadingTrendGraphicRequest,
    schemas.GetNotesTrendGraphicRequest,
    schemas.GetCompletedMaterialsTrendGraphicRequest,
    schemas.GetRepeatedMaterialsTrendGraphicRequest,
    schemas.GetOutlinedMaterialsTrendGraphicRequest,
    schemas.GetTotalReadGraphicRequest,
]


@pytest.mark.parametrize("model", LAST_DAYS_REQUESTS)
class TestLastDaysRequests:
    @pytest.mark.parametrize("last_days", [1, 7, 10**6])
    def test_positive_last_days_is_accepted(self, model, last_days):
        assert model(last_days=last_days).last_days == last_days

    @pytest.mark.parametrize("last_days", [0, -1, 1.5, "x", None])
    def test_non_positive_or_non_int_last_days_is_rejected(self, model, last_days):
        with pytest.raises(ValidationError, match="last_days"):
            model(last_days=last_days)

    def test_last_days_is_required(self, model):
        with pytest.raises(ValidationError, match="last_days"):
            model()


class TestGetReadingProgressGraphicRequest:
    def test_valid_request(self):
        request = schemas.GetReadingProgressGraphicRequest(
            material_id=str(UUID(int=1)),
            last_days=1,
        )

        assert (request.material_id, request.last_days) == (UUID(int=1), 1)

    @pytest.mark.parametrize("last_days", [0, -1])
    def test_non_positive_last_days_is_rejected(self, last_days):
        with pytest.raises(ValidationError, match="last_days"):
            schemas.GetReadingProgressGraphicRequest(
                material_id=UUID(int=1),
                last_days=last_days,
            )

    def test_invalid_material_id_is_rejected(self):
        with pytest.raises(ValidationError, match="material_id"):
            schemas.GetReadingProgressGraphicRequest(material_id="x", last_days=1)


COUNTERS = {
    "materials_count": 1,
    "reading_log_count": 2,
    "notes_count": 3,
    "cards_count": 4,
    "repeats_count": 5,
    "note_repeats_history_count": 0,
}


@pytest.mark.parametrize("model", [schemas.BackupResponse, schemas.RestoreResponse])
class TestCountersResponses:
    def test_zero_and_positive_counters_are_accepted(self, model):
        assert model(**COUNTERS).model_dump() == COUNTERS

    @pytest.mark.parametrize("field", list(COUNTERS))
    def test_negative_counter_is_rejected(self, model, field):
        with pytest.raises(ValidationError, match=field):
            model(**(COUNTERS | {field: -1}))

    @pytest.mark.parametrize("field", list(COUNTERS))
    def test_counter_is_required(self, model, field):
        counters = {name: value for name, value in COUNTERS.items() if name != field}

        with pytest.raises(ValidationError, match=field):
            model(**counters)


def test_span_stats_response_rejects_negative_values():
    record = {"date": datetime.date(2024, 1, 1), "amount": 0}
    values = {
        "total": 0,
        "would_be_total": 0,
        "zero_days": 0,
        "mean": 0,
        "median": 0,
        "max_record": record,
        "min_record": record,
    }

    assert schemas._SpanStatsResponse(**values).max_record.amount == 0
    with pytest.raises(ValidationError, match="mean"):
        schemas._SpanStatsResponse(**(values | {"mean": -0.01}))
    with pytest.raises(ValidationError, match="amount"):
        schemas._SpanStatsResponse(**(values | {"min_record": record | {"amount": -1}}))
