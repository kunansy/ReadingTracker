from decimal import Decimal
from enum import Enum
from typing import TypeAlias


class MaterialTypesEnum(str, Enum):
    book = "book"
    article = "article"
    course = "course"
    lecture = "lecture"
    audiobook = "audiobook"


MEANS: TypeAlias = dict[MaterialTypesEnum, Decimal]
