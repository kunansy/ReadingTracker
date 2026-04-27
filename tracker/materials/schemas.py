import datetime
import typing
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BeforeValidator, HttpUrl, PositiveInt, NonNegativeInt

from tracker.common.schemas import CustomBaseModel, skip_empty_value, MinMax
from tracker.models import enums
from tracker.models.enums import MaterialTypesEnum


class GetMaterialItem(CustomBaseModel):
    material_id: UUID
    title: str
    authors: str
    pages: NonNegativeInt
    material_type: enums.MaterialTypesEnum
    tags: Annotated[str | None, BeforeValidator(skip_empty_value)] = None
    link: Annotated[HttpUrl | None, BeforeValidator(skip_empty_value)] = None
    added_at: datetime.datetime
    is_outlined: bool
    index: PositiveInt


class OkResponse(CustomBaseModel):
    ok: bool


class MaterialEstimate(CustomBaseModel):
    material: GetMaterialItem
    will_be_started: datetime.date
    will_be_completed: datetime.date
    expected_duration: PositiveInt


class MaterialStatistics(CustomBaseModel):
    material: GetMaterialItem
    started_at: datetime.date
    duration: int
    lost_time: NonNegativeInt
    total: int
    min_record: MinMax | None
    max_record: MinMax | None
    mean: NonNegativeInt
    notes_count: NonNegativeInt
    remaining_pages: NonNegativeInt | None = None
    remaining_days: NonNegativeInt | None = None
    completed_at: datetime.date | None = None
    total_reading_duration: str | None = None
    # date when the material would be completed
    # according to mean read pages count
    would_be_completed: datetime.date | None = None
    percent_completed: float


class RepeatingQueueItem(CustomBaseModel):
    material_id: UUID
    title: str
    pages: NonNegativeInt
    material_type: enums.MaterialTypesEnum
    is_outlined: bool
    notes_count: NonNegativeInt
    cards_count: NonNegativeInt
    repeats_count: NonNegativeInt
    completed_at: datetime.datetime | None
    last_repeated_at: datetime.datetime | None
    priority_days: int
    priority_months: float


class GetMaterialsQueueResponse(CustomBaseModel):
    estimates: list[MaterialEstimate]
    mean: dict[MaterialTypesEnum, Decimal]


class GetReadingMaterialsResponse(CustomBaseModel):
    statistics: list[MaterialStatistics]


class GetCompletedMaterialsResponse(CustomBaseModel):
    statistics: list[MaterialStatistics]


class GetRepeatingQueueResponse(CustomBaseModel):
    repeating_queue: list[RepeatingQueueItem]


class GetMaterialResponse(CustomBaseModel):
    material: GetMaterialItem


class CreateMaterialRequest(CustomBaseModel):
    title: str
    authors: str
    pages: PositiveInt
    material_type: enums.MaterialTypesEnum
    tags: Annotated[str | None, BeforeValidator(skip_empty_value)] = None
    link: Annotated[HttpUrl | None, BeforeValidator(skip_empty_value)] = None

    def get_link(self) -> str | None:
        if link := self.link:
            return str(link)
        return None


class CreateMaterialResponse(CustomBaseModel):
    material_id: UUID


class UpdateMaterialRequest(CreateMaterialRequest):
    material_id: UUID


class UpdateMaterialResponse(CreateMaterialRequest):
    material_id: UUID


class ParsedMaterialResponse(CustomBaseModel):
    authors: str
    title: str
    type: str
    link: HttpUrl
    duration: int | None = None


class SearchParams(CustomBaseModel):
    material_type: enums.MaterialTypesEnum | None | Literal[""] = None
    outlined: Literal["outlined", "not_outlined", "all"] | None = None
    tags_query: str | None = None

    @property
    def is_outlined(self) -> bool | None:
        if self.outlined == "outlined":
            return True
        if self.outlined == "not_outlined":
            return False
        if self.outlined in ("all", None):
            return None

        raise ValueError(f"Invalid outline: {self.outlined!r}")

    def requested_tags(self) -> set[str]:
        if not (tags_query := self.tags_query):
            return set()

        return {tag.strip() for tag in tags_query.split() if tag.strip()}

    def get_material_type(self) -> enums.MaterialTypesEnum | None:
        if isinstance(self.material_type, enums.MaterialTypesEnum):
            return self.material_type
        return None


class IsMaterialReadingResponse(CustomBaseModel):
    is_reading: bool


class GetQueueEdgeResponse(CustomBaseModel):
    index: PositiveInt


class GetMaterialTagsResponse(CustomBaseModel):
    tags: set[str]


class GetAuthorsResponse(CustomBaseModel):
    authors: typing.Iterable[str]


class SwapOrderRequest(CustomBaseModel):
    material_id: UUID
    index: int


class StartMaterialRequest(CustomBaseModel):
    started_at: datetime.date | None = None


class CompleteMaterialRequest(CustomBaseModel):
    completed_at: datetime.date | None = None


class ParseLinkRequest(CustomBaseModel):
    link: HttpUrl
