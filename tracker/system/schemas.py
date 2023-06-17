import datetime
from typing import Any

from fastapi import Form
from pydantic import validator

from tracker.common.schemas import CustomBaseModel


class GetSpanReportRequest(CustomBaseModel):
    start: datetime.date
    stop: datetime.date

    def __init__(self,
                 start: datetime.date = Form(...),
                 stop: datetime.date = Form(None)) -> None:
        stop = stop or datetime.date.today()
        super().__init__(
            start=start,
            stop=stop
        )

    @validator('stop')
    def validate_start_less_than_stop(cls,
                                      stop: datetime.date,
                                      config: dict[str, Any]) -> datetime.date:
        start = config['start']
        assert stop < start, "Stop must be less than start"

        return stop

    @property
    def size(self) -> int:
        return (self.stop - self.start).days + 1

    def create_span_ago(self, ago: int) -> "GetSpanReportRequest":
        return self.__class__(
            start=self.start - datetime.timedelta(days=ago),
            stop=self.stop - datetime.timedelta(days=ago),
        )
