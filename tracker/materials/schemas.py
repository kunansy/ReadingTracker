from pydantic import BaseModel, conint, constr, validator


class Material(BaseModel):
    title: constr(strip_whitespace=True, min_length=1) # type: ignore
    authors: constr(strip_whitespace=True, min_length=1) # type: ignore
    pages: conint(gt=0) # type: ignore
    tags: constr(strip_whitespace=True) # type: ignore

    @validator('title', 'authors', 'tags')
    def validate_title(cls,
                       item: str) -> str:
        if '"' in item or '«' in item or '»' in item:
            raise ValueError("Brackets are unexpected here")
        return item
