import datetime
from typing import Any

from fastapi import Form
from pydantic import validator

from tracker.common.schemas import CustomBaseModel


class GetSpanReportRequest(CustomBaseModel):
    start: datetime.date
    stop: datetime.date | None = None

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
