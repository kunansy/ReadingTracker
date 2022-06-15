from fastapi import Form
from pydantic import BaseModel, conint, HttpUrl

from tracker.models import enums


class Material(BaseModel):
    title: str
    authors: str
    pages: conint(ge=1)
    material_type: enums.MaterialTypesEnum
    tags: str | None = None
    link: HttpUrl | None = None

    def __init__(self,
                 title: str = Form(...),
                 authors: str = Form(...),
                 pages: int = Form(...),
                 material_type: enums.MaterialTypesEnum = Form(...),
                 tags: str | None = Form(None),
                 link: HttpUrl | None = Form(None)) -> None:
        super().__init__(
            title=title,
            authors=authors,
            pages=pages,
            material_type=material_type,
            tags=tags,
            link=link
        )
