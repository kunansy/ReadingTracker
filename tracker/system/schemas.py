import datetime
from typing import Any

from fastapi import Form
from pydantic import validator

from tracker.common.schemas import CustomBaseModel
from tracker.models import enums


class GetSpanReportRequest(CustomBaseModel):
    start: datetime.date
    stop: datetime.date

    def __init__(self,
                 start: datetime.date = Form(...),
                 stop: datetime.date | None = Form(None)) -> None:
        # way to check Form value is None
        if not isinstance(stop, str):
            stop = datetime.date.today()

        super().__init__(
            start=start,
            stop=stop
        )

    @validator('stop', pre=False, always=True)
    def validate_start_less_than_stop(cls,
                                      stop: datetime.date,
                                      values: dict[str, Any]) -> datetime.date:
        start = values['start']
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


class GetSpanReportResponse(CustomBaseModel):
    completed_materials: dict[enums.MaterialTypesEnum, int]
    total_materials_completed: int

    read_items: dict[enums.MaterialTypesEnum, int]
    reading_total: int
    reading_median: float
    reading_mean: float
    reading_lost_count: int
    reading_zero_days: int
    reading_would_be_total: int

    notes_total: int
    notes_median: float
    notes_mean: float
    notes_lost_count: int
    notes_zero_days: int
    notes_would_be_total: int