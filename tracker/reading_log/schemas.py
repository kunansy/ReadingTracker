import datetime
from uuid import UUID

from fastapi import Form
from pydantic import NonNegativeInt, conint

from tracker.common.schemas import CustomBaseModel
from tracker.models import enums


class LogRecord(CustomBaseModel):
    material_id: UUID
    count: conint(ge=1)
    date: datetime.date

    def __init__(
        self,
        material_id: UUID = Form(...),
        count: int = Form(...),
        date: datetime.date = Form(...),
    ):
        super().__init__(material_id=material_id, count=count, date=date)


class CompletionInfoSchema(CustomBaseModel):
    material_pages: NonNegativeInt
    material_type: enums.MaterialTypesEnum
    pages_read: NonNegativeInt
    read_days: NonNegativeInt
