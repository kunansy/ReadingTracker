from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict


class CustomBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def str_to_uuid(v: Literal[""] | UUID | None) -> UUID | None:
    if not v:
        return None
    return v


DEFAULT_UUID = Annotated[UUID | None, BeforeValidator(str_to_uuid)]
