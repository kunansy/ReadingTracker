from typing import Any
from uuid import UUID

from sqlalchemy import Table


DOC = dict[str, Any]

SA_TYPE_MAPPING = {}


class ElasticsearchError(Exception):
    pass


class AsyncElasticIndex:
    def __init__(self,
                 table: Table) -> None:
        self.__table = table
        self._url = settings.ELASTIC_URL
        self._timeout = aiohttp.ClientTimeout(settings.ELASTIC_TIMEOUT)

    def _create_index_query(self) -> DOC:
        return {
            "mappings": {
                "doc": {
                    "properties": {
                        field_name: SA_TYPE_MAPPING[field_type]
                        for field_name, field_type in self.__table.columns.items()
                    }
                }
            }
        }

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
