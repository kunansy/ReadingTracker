from datetime import datetime
from uuid import UUID

from fastapi import Form
from pydantic import BaseModel, conint


class LogRecord(BaseModel):
    material_id: UUID
    count: conint(ge=1)
    date: datetime.date

    def __init__(self,
                 material_id: UUID = Form(...),
                 count: int = Form(...),
                 date: datetime.date = Form(...)):
        super().__init__(
            material_id=material_id,
            count=count,
            date=date
        )
