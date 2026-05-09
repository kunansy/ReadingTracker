import datetime
from uuid import UUID

from pydantic import NonNegativeInt, PositiveInt

from tracker.common.schemas import CustomBaseModel


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
    count: PositiveInt
    date: datetime.date


class GetReadingLogResponse(CustomBaseModel):
    reading_log: _GetLogRecordItem


class GetMaterialReadingNowResponse(CustomBaseModel):
    material_id: UUID
