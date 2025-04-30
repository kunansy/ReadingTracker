from typing import Literal
from uuid import UUID

from pydantic import HttpUrl, conint

from tracker.common.schemas import CustomBaseModel
from tracker.models import enums


class Material(CustomBaseModel):
    title: str
    authors: str
    pages: conint(ge=1)
    material_type: enums.MaterialTypesEnum
    tags: str | None = None
    link: HttpUrl | None = None

    def get_link(self) -> str | None:
        if link := self.link:
            return str(link)
        return None


class UpdateMaterial(Material):
    material_id: UUID


class ParsedMaterial(CustomBaseModel):
    authors: str
    title: str
    type: str
    link: str
    duration: int | None = None


class SearchParams(CustomBaseModel):
    material_type: enums.MaterialTypesEnum | None | Literal[""] = None
    outlined: Literal["outlined", "not_outlined", "all", None] = None
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
