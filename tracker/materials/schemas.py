from fastapi import Form
from pydantic import BaseModel, conint, HttpUrl


class Material(BaseModel):
    title: str
    authors: str
    pages: conint(ge=1)
    tags: str | None = None
    link: HttpUrl | None = None

    def __init__(self,
                 title: str = Form(...),
                 authors: str = Form(...),
                 pages: int = Form(...),
                 tags: str | None = Form(None),
                 link: HttpUrl | None = Form(None)) -> None:
        super().__init__(
            title=title,
            authors=authors,
            pages=pages,
            tags=tags,
            link=link
        )
