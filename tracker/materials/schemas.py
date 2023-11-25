from uuid import UUID

from fastapi import Form
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

    def __init__(
        self,
        title: str = Form(...),
        authors: str = Form(...),
        pages: int = Form(...),
        material_type: enums.MaterialTypesEnum = Form(...),
        tags: str | None = Form(None),
        link: HttpUrl | None = Form(None),
        **kwargs,
    ) -> None:
        super().__init__(
            title=title,
            authors=authors,
            pages=pages,
            material_type=material_type,
            tags=tags,
            link=link,
            **kwargs,
        )

    def get_link(self) -> str | None:
        if link := self.link:
            return str(link)
        return None


class UpdateMaterial(Material):
    material_id: UUID

    def __init__(
        self,
        material_id: UUID = Form(...),
        title: str = Form(...),
        authors: str = Form(...),
        pages: int = Form(...),
        material_type: enums.MaterialTypesEnum = Form(...),
        tags: str | None = Form(None),
        link: HttpUrl | None = Form(None),
    ) -> None:
        super().__init__(
            material_id=material_id,
            title=title,
            authors=authors,
            pages=pages,
            material_type=material_type,
            tags=tags,
            link=link,
        )
