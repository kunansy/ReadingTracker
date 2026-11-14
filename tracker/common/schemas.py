import datetime
import re
from typing import Annotated, Final
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, NonNegativeInt, constr


MAX_SEARCH_QUERY_LENGTH: Final[int] = 512
TAG_PATTERN: Final[re.Pattern[str]] = re.compile(r"^(\w+)$")


class CustomBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class MinMax(CustomBaseModel):
    log_id: UUID
    material_id: UUID
    material_title: str
    count: NonNegativeInt
    date: datetime.date


def normalize_tags(raw: str) -> list[str]:
    """Parse whitespace-separated, optionally `#`-prefixed tags."""
    normalized = set(raw.lower().replace("#", "").split())
    if any(not TAG_PATTERN.match(tag) for tag in normalized):
        raise ValueError("Invalid tags")
    return sorted(normalized)


def _normalize_tags_query(tags_query: str | None) -> str | None:
    return " ".join(normalize_tags(tags_query or "")) or None


def _dedupe_tags(tags: list[str]) -> list[str]:
    return sorted(set(tags))


type Tag = constr(pattern=TAG_PATTERN.pattern, to_lower=True, strip_whitespace=True)
Tags = Annotated[list[Tag], AfterValidator(_dedupe_tags)]
TagsQuery = Annotated[
    str | None,
    Field(max_length=MAX_SEARCH_QUERY_LENGTH),
    AfterValidator(_normalize_tags_query),
]
