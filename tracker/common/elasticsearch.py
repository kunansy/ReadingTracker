from typing import Any
from uuid import UUID

import aiohttp
from sqlalchemy import Table

from tracker.common import settings
from tracker.common.log import logger

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

    async def create_index(self) -> DOC:
        query = self._create_index_query()
        async with aiohttp.ClientSession(timeout=self._timeout) as ses:
            try:
                resp = await ses.put(self._url, json=query)
                resp.raise_for_status()
                json = await resp.json()
            except Exception as e:
                logger.exception("Error creating index")
                raise ElasticsearchError(e) from None

        logger.info("Index created: %s", json)
        return json

    async def get(self, doc_id: UUID) -> DOC:
        url = f"{self._url}/_doc/{doc_id}"
        async with aiohttp.ClientSession(timeout=self._timeout) as ses:
            try:
                resp = await ses.get(url)
                resp.raise_for_status()
                json = await resp.json()
            except Exception as e:
                logger.exception("Error getting document")
                raise ElasticsearchError(e) from None

        return json

    async def add(self,
                  *,
                  doc: DOC,
                  doc_id: UUID) -> DOC:
        """ Create or update the document """
        url = f"{self._url}/_doc/{doc_id}"
        async with aiohttp.ClientSession(timeout=self._timeout) as ses:
            try:
                resp = await ses.put(url, json=doc)
                resp.raise_for_status()
                json = await resp.json()
            except Exception as e:
                logger.exception("Error adding document")
                raise ElasticsearchError(e) from None

        return json

    async def delete(self, doc_id: UUID) -> DOC:
        url = f"{self._url}/_doc/{doc_id}"
        async with aiohttp.ClientSession(timeout=self._timeout) as ses:
            try:
                resp = await ses.delete(url)
                resp.raise_for_status()
                json = await resp.json()
            except Exception as e:
                logger.exception("Error deleting document")
                raise ElasticsearchError(e) from None

        return json

    async def mathc(self, query: str) -> list[DOC]:
        pass

    async def multi_match(self, query: str) -> list[DOC]:
        pass
