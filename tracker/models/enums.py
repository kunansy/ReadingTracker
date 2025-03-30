from decimal import Decimal
from enum import StrEnum, auto


class MaterialTypesEnum(StrEnum):
    book = auto()
    article = auto()
    course = auto()
    lecture = auto()
    audiobook = auto()


type MEANS = dict[MaterialTypesEnum, Decimal]
