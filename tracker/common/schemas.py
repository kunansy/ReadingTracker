from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict


if TYPE_CHECKING:
    from uuid import UUID


class CustomBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def skip_empty_value(v: Literal[""] | UUID | None) -> UUID | None:
    """Needed to work with html forms, that sends empty string as default."""
    if not v:
        return None
    return v
