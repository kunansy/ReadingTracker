import datetime
from uuid import UUID

from pydantic import NonNegativeInt, conint

from tracker.common.schemas import CustomBaseModel
from tracker.models import enums


class LogRecord(CustomBaseModel):
    material_id: UUID
    count: conint(ge=1)
    date: datetime.date


class CompletionInfoSchema(CustomBaseModel):
    material_pages: NonNegativeInt
    material_type: enums.MaterialTypesEnum
    pages_read: NonNegativeInt
    read_days: NonNegativeInt
