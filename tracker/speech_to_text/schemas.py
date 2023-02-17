from pydantic import validator

from tracker.common.schemas import CustomBaseModel


class TranscriptTextResponse(CustomBaseModel):
    transcript: str
    confidence: float

    @validator('confidence')
    def convert_to_percent(cls, value: float) -> float:
        return round(value * 100, 2)
