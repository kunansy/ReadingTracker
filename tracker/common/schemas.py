from typing import Any, Callable

import orjson as orjson
from pydantic import BaseModel


def orjson_dumps(v: Any, *, default: Callable[[Any], Any] | None = None) -> str:
    # orjson.dumps returns bytes, to match standard json.dumps we need to decode
    return orjson.dumps(v, default=default).decode()


class CustomBaseModel(BaseModel):
    class Config:
        json_loads = orjson.loads
        json_dumps = orjson_dumps
        extra = 'forbid'
