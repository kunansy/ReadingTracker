from pydantic import BaseModel, conint, constr, validator


def format_string(string: str,
                  ends: tuple[str, ...]) -> str:
    string = ' '.join(string.replace('\n', '<br/>').split())

    return f"{string[0].upper()}{string[1:]}" \
           f"{'.' * (not string.endswith(ends))}"


class Note(BaseModel):
    material_id: conint(gt=0) # type: ignore
    content: constr(strip_whitespace=True, min_length=1) # type: ignore
    chapter: conint(ge=0) # type: ignore
    # TODO: validate that the page is <= than material size
    page: conint(gt=0) # type: ignore

    @validator('material_id')
    def validate_material_assigned(cls,
                                   material_id: int) -> int:
        # TODO: remove business logic from here
        # if not database.is_material_assigned(material_id):
        #     raise ValueError(f"Material {material_id=} is not assigned")

        return material_id

    @validator('content')
    def format_content(cls,
                       content: str) -> str:
        return format_string(content, ('.',))
