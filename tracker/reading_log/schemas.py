import datetime

from pydantic import BaseModel, PositiveInt, validator


class LogRecord(BaseModel):
    material_id: PositiveInt # type: ignore
    date: datetime.date # type: ignore
    count: PositiveInt # type: ignore

    @validator('date')
    def validate_date(cls,
                      date: datetime.date) -> datetime.date:
        assert date <= datetime.datetime.utcnow().date(), "You cannot set log to the future"
        return date
