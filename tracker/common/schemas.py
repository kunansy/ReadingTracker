import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, NonNegativeInt


class CustomBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class MinMax(CustomBaseModel):
    log_id: UUID
    material_id: UUID
    material_title: str
    count: NonNegativeInt
    date: datetime.date


def skip_empty_value(v: Literal[""] | UUID | None) -> UUID | None:
    """Needed to work with html forms, that sends empty string as default."""
    if not v:
        return None
    return v
