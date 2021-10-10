import datetime

from pydantic import BaseModel, conint, validator

from tracker.common import database


class LogRecord(BaseModel):
    material_id: conint(gt=0) # type: ignore
    date: datetime.date # type: ignore
    count: conint(gt=0) # type: ignore

    @validator('date')
    def validate_date(cls,
                      date: datetime.date) -> datetime.date:
        assert date <= datetime.datetime.utcnow(), "You cannot set log to the future"
        return date

    @validator('material_id')
    def validate_material_reading(cls,
                                  material_id: int) -> int:
        assert database.is_material_reading(material_id), \
            f"Material {material_id=} is not reading"
        return material_id
