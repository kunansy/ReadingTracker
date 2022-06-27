from typing import Any
from uuid import UUID

import aiohttp
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from tracker.common import settings
from tracker.common.log import logger


DOC = dict[str, Any]

SA_TYPE_MAPPING = {
    sa.Unicode: "text",
    sa.Text: "text",
    PG_UUID: "text",
    sa.DateTime: "date",
    sa.Integer: "integer",
    sa.Boolean: "boolean",
}


def _get_es_type(sa_type: object) -> str | None:
    for key, value in SA_TYPE_MAPPING.items():
        if isinstance(sa_type, key):
            return value


class ElasticsearchError(Exception):
    pass


class AsyncElasticIndex:
    def __init__(self,
                 table: sa.Table) -> None:
        self.__table = table
        self._url = settings.ELASTIC_URL
        self._timeout = aiohttp.ClientTimeout(settings.ELASTIC_TIMEOUT)
        self._headers = {
            "Content-Type": "application/json"
        }

    @property
    def name(self) -> str:
        return self.__table.name

    def _create_index_query(self) -> DOC:
        return {
            "mappings": {
                "properties": {
                    field.name: {"type": _get_es_type(field.type)}
                    for field in self.__table.columns.values()
                }
            }
        }

    async def create_index(self) -> DOC:
        query = self._create_index_query()
        url = f"{self._url}/{self.name}"

        async with aiohttp.ClientSession(timeout=self._timeout) as ses:
            try:
                resp = await ses.put(url, json=query, headers=self._headers)
                json, status = await resp.json(), resp.status
                resp.raise_for_status()
            except Exception:
                msg = f"Error creating index ({status=}): {json=}"
                logger.exception(msg)
                raise ElasticsearchError(msg) from None

        logger.info("Index created (status=%s): %s", status, json)
        return json

    async def get(self, doc_id: UUID) -> DOC:
        url = f"{self._url}/{self.name}/_doc/{doc_id}"
        async with aiohttp.ClientSession(timeout=self._timeout) as ses:
            try:
                resp = await ses.get(url, headers=self._headers)
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
        url = f"{self._url}/{self.name}/_doc/{doc_id}"
        async with aiohttp.ClientSession(timeout=self._timeout) as ses:
            try:
                resp = await ses.put(url, json=doc, headers=self._headers)
                resp.raise_for_status()
                json = await resp.json()
            except Exception as e:
                logger.exception("Error adding document")
                raise ElasticsearchError(e) from None

        return json

    async def delete(self, doc_id: UUID) -> DOC:
        url = f"{self._url}/{self.name}/_doc/{doc_id}"
        async with aiohttp.ClientSession(timeout=self._timeout) as ses:
            try:
                resp = await ses.delete(url, headers=self._headers)
                resp.raise_for_status()
                json = await resp.json()
            except Exception as e:
                logger.exception("Error deleting document")
                raise ElasticsearchError(e) from None

        return json

    async def match(self, query: str, field: str) -> list[DOC]:
        uel = f"{self._url}/{self.name}/_search"
        body = {
            "query": {
                "match": {
                    field: query,
                }
            }
        }

        async with aiohttp.ClientSession(timeout=self._timeout) as ses:
            try:
                resp = await ses.put(uel, json=body, headers=self._headers)
                resp.raise_for_status()
                json = await resp.json()
            except Exception as e:
                logger.exception("Error searching")
                raise ElasticsearchError(e) from None

        return json

    async def multi_match(self, query: str) -> list[DOC]:
        uel = f"{self._url}/{self.name}/_search"
        body = {
            "query": {
                "multi_match": {
                    "query": query,
                    "fields": ["*"]
                }
            }
        }

        async with aiohttp.ClientSession(timeout=self._timeout) as ses:
            try:
                resp = await ses.put(uel, json=body, headers=self._headers)
                resp.raise_for_status()
                json = await resp.json()
            except Exception as e:
                logger.exception("Error searching")
                raise ElasticsearchError(e) from None

        return json
