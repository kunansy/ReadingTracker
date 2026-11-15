import datetime
from typing import Annotated, Final
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    NonNegativeInt,
    StringConstraints,
    TypeAdapter,
    ValidationError,
)


MAX_SEARCH_QUERY_LENGTH: Final[int] = 512
TAG_PATTERN: Final[str] = r"^[\p{L}\p{N}_]+$"
MAX_TAG_LENGTH: Final[int] = 128
MAX_TAGS: Final[int] = 32


class CustomBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class MinMax(CustomBaseModel):
    log_id: UUID
    material_id: UUID
    material_title: str
    count: NonNegativeInt
    date: datetime.date


def _canonical_tag(value: object) -> object:
    if not isinstance(value, str):
        return value
    return value.strip().lower().lstrip("#").strip("_")


def _dedupe_tags(tags: list[str]) -> list[str]:
    unique = sorted(set(tags))
    if len(unique) > MAX_TAGS:
        raise ValueError(f"at most {MAX_TAGS} tags")
    return unique


type Tag = Annotated[
    Annotated[str, StringConstraints(pattern=TAG_PATTERN, max_length=MAX_TAG_LENGTH)],
    BeforeValidator(_canonical_tag),
]
type Tags = Annotated[
    list[Tag],
    Field(json_schema_extra={"maxItems": MAX_TAGS}),
    AfterValidator(_dedupe_tags),
]

_TAG_ADAPTER: Final[TypeAdapter[str]] = TypeAdapter(Tag)


def normalize_tags(raw: str) -> list[str]:
    """Split whitespace-separated tags, normalize each as `Tag`, dedupe and sort them.

    Raises ValueError if a tag does not satisfy `Tag`.
    """
    try:
        tags = {_TAG_ADAPTER.validate_python(tag) for tag in raw.split()}
    except ValidationError:
        raise ValueError("Invalid tags") from None
    return sorted(tags)


def _normalize_tags_query(tags_query: str | None) -> str | None:
    return " ".join(normalize_tags(tags_query or "")) or None


TagsQuery = Annotated[
    str | None,
    Field(max_length=MAX_SEARCH_QUERY_LENGTH),
    AfterValidator(_normalize_tags_query),
]


class TagsSearchParams(CustomBaseModel):
    tags_query: TagsQuery = None

    def requested_tags(self) -> set[str]:
        return set((self.tags_query or "").split())
