from enum import Enum


class MaterialTypesEnum(str, Enum):
    book = 'book'
    article = 'article'
    course = 'course'
    lecture = 'lecture'
