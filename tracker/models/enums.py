from decimal import Decimal
from enum import Enum


class MaterialTypesEnum(str, Enum):
    book = "book"
    article = "article"
    course = "course"
    lecture = "lecture"
    audiobook = "audiobook"


type MEANS = dict[MaterialTypesEnum, Decimal]
