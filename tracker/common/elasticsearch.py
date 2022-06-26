from typing import Any
from uuid import UUID

from sqlalchemy import Table


DOC = dict[str, Any]


class AsyncElasticIndex:
    def __init__(self,
                 table: Table) -> None:
        pass

    async def create_index(self) -> None:
        pass

    async def get(self, doc_id: UUID) -> DOC:
        pass

    async def add(self,
                  *,
                  doc: DOC,
                  doc_id: UUID) -> None:
        """ Create or update the document """
        pass

    async def delete(self, doc_id: UUID) -> None:
        pass

    async def mathc(self, query: str) -> list[DOC]:
        pass

    async def multi_match(self, query: str) -> list[DOC]:
        pass
