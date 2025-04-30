from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CustomBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def skip_empty_value(v: Literal[""] | UUID | None) -> UUID | None:
    """Needed to work with html forms, that sends empty string as default."""
    if not v:
        return None
    return v
