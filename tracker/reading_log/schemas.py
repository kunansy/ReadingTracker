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


class ListReadingLogsRequest(CustomBaseModel):
    material_id: UUID | None


class ListReadingLogsResponse(CustomBaseModel):
    items: list[LogRecord]


class CreateReadingLogsResponse(CustomBaseModel):
    log_id: UUID


class GetReadingLogRequest(CustomBaseModel):
    reading_log: LogRecord
