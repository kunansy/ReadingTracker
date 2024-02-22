from typing import Any

import orjson
from fastapi.encoders import jsonable_encoder
from fastapi_cache import Coder
from pydantic import BaseModel, ConfigDict


class CustomBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ORJSONEncoder(Coder):
    @classmethod
    def encode(cls, value: Any) -> bytes:  # noqa: ANN102
        return orjson.dumps(
            value,
            default=jsonable_encoder,
            option=orjson.OPT_NON_STR_KEYS | orjson.OPT_SERIALIZE_NUMPY,
        )

    @classmethod
    def decode(cls, value: bytes) -> Any:  # noqa: ANN102
        return orjson.loads(value)
