import datetime
from uuid import UUID

from pydantic import NonNegativeInt, conint

from tracker.common.schemas import CustomBaseModel
from tracker.models import enums


class CompletionInfoSchema(CustomBaseModel):
    material_pages: NonNegativeInt
    material_type: enums.MaterialTypesEnum
    pages_read: NonNegativeInt
    read_days: NonNegativeInt


class _GetLogRecordItem(CustomBaseModel):
    log_id: UUID
    material_id: UUID
    # because of 'without material' notes
    count: NonNegativeInt
    date: datetime.date


class ListReadingLogsResponse(CustomBaseModel):
    items: list[_GetLogRecordItem]


class CreateReadingLogsResponse(CustomBaseModel):
    log_id: UUID


class CreateReadingLogsRequest(CustomBaseModel):
    material_id: UUID
    count: conint(ge=1)
    date: datetime.date


class GetReadingLogResponse(CustomBaseModel):
    reading_log: _GetLogRecordItem


class ListMaterialsTitles(CustomBaseModel):
    items: dict[UUID, str]
