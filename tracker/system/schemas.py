import datetime

from pydantic import NonNegativeInt, field_validator, Field
from pydantic_core.core_schema import ValidationInfo

from tracker.common.schemas import CustomBaseModel
from tracker.models import enums


def _now() -> datetime.date:
    return datetime.datetime.now(tz=datetime.UTC).replace(tzinfo=None).date()


class GetSpanReportRequest(CustomBaseModel):
    start: datetime.date
    stop: datetime.date = Field(default_factory=_now)

    @field_validator("stop")
    def validate_start_less_than_stop(
        cls,
        stop: datetime.date,
        info: ValidationInfo,
    ) -> datetime.date:
        start = info.data["start"]
        assert stop > start, "Start must be less than stop"

        return stop

    @property
    def size(self) -> int:
        return (self.stop - self.start).days + 1

    def create_span_ago(self, ago: int) -> "GetSpanReportRequest":
        if ago <= 0:
            raise ValueError(f"Ago must be > 0, {ago!r} found")

        return self.__class__(
            start=self.start - datetime.timedelta(days=ago),
            stop=self.stop - datetime.timedelta(days=ago),
        )


class _SpanStats(CustomBaseModel):
    total: int
    median: float
    mean: float
    lost_count: int
    zero_days: int
    would_be_total: int


class GetSpanReportResponse(CustomBaseModel):
    completed_materials: dict[enums.MaterialTypesEnum, int]
    total_materials_completed: int

    read_items: dict[enums.MaterialTypesEnum, int]
    reading: _SpanStats
    notes: _SpanStats

    repeats_total: int
    repeat_materials_count: int


class BackupResponse(CustomBaseModel):
    materials_count: NonNegativeInt
    reading_log_count: NonNegativeInt
    statuses_count: NonNegativeInt
    notes_count: NonNegativeInt
    cards_count: NonNegativeInt
    repeats_count: NonNegativeInt
    note_repeats_history_count: NonNegativeInt
