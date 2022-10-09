import datetime
from types import UnionType
from typing import Any, Type, NamedTuple
from uuid import UUID

import aiohttp

from tracker.common import settings
from tracker.common.log import logger
from tracker.common.schemas import orjson_dumps


DOC = dict[str, Any]
UID = UUID | str

ELASTIC_TYPES_MAPPING = {
    str: "text",
    UUID: "text",
    datetime.datetime: "date",
    datetime.date: "date",
    int: "integer",
    bool: "boolean",
}


def _map_elastic_type(type_: object) -> str | None:
    if isinstance(type_, UnionType):
        return _map_elastic_type(type_.__args__[0])

    for key, value in ELASTIC_TYPES_MAPPING.items():
        if type_ is key:
            return value
    return None


def _serialize_datetime(field: Any) -> str:
    if isinstance(field, datetime.datetime):
        return field.isoformat()
    return field


def _serialize(doc: DOC) -> DOC:
    return {
        _serialize_datetime(key): _serialize_datetime(value)
        for key, value in doc.items()
    }


class ElasticsearchException(Exception):
    pass


class Response(NamedTuple):
    status: int
    json: DOC


class AsyncElasticIndex:
    def __init__(self,
                 tuple: Type) -> None:
        self.__tuple = tuple
        self._url = settings.ELASTIC_URL
        self._timeout = aiohttp.ClientTimeout(settings.ELASTIC_TIMEOUT)
        self._headers = {
            "Content-Type": "application/json"
        }

    @property
    def name(self) -> str:
        return self.__tuple.__class__.__name__.lower()

    def _create_index_query(self) -> DOC:
        analyzer = {
            "settings": {
                "index": {
                    "analysis": {
                        "analyzer": {
                            "ru": {
                                "tokenizer": "standard",
                                "filter": [
                                    "lowercase",
                                    "ru_RU",
                                ]
                            }
                        },
                        "filter": {
                            "ru_RU": {
                                "type": "hunspell",
                                "locale": "ru_RU",
                                "dedup": True
                            }
                        }
                    }
                }
            }
        }
        properties = {}
        for field_name, field_type in self.__tuple.__annotations__.items():
            field_type = _map_elastic_type(field_type)

            properties[field_name] = {
                "type": field_type
            }
            if field_type == "text":
                properties[field_name]["analyzer"] = "ru"

        mappings = {
            "mappings": {
                "properties": properties
            }
        }

        return {
            **analyzer,
            **mappings,
        }

    async def __get(self,
                    url: str,
                    query: DOC | None = None) -> Response:
        async with aiohttp.ClientSession(timeout=self._timeout, json_serialize=orjson_dumps) as ses:
            try:
                resp = await ses.get(url, json=query, headers=self._headers)
                status, json = resp.status, await resp.json()
                resp.raise_for_status()
            except Exception as e:
                msg = f"GET '{url=}', '{query=}': {repr(e)}"
                logger.exception(msg)
                raise ElasticsearchException(msg)

        return Response(status=status, json=json)

    async def __put(self,
                    url: str,
                    body: DOC | None = None) -> Response:
        async with aiohttp.ClientSession(timeout=self._timeout, json_serialize=orjson_dumps) as ses:
            try:
                resp = await ses.put(url, json=body, headers=self._headers)
                status, json = resp.status, await resp.json()
                resp.raise_for_status()
            except Exception as e:
                msg = f"PUT '{url=}', '{body=}': {repr(e)}"
                logger.exception(msg)
                raise ElasticsearchException(msg)

        return Response(status=status, json=json)

    async def create_index(self) -> DOC:
        query = self._create_index_query()
        url = f"{self._url}/{self.name}"

        status, json = await self.__put(url, query)

        logger.info("Index created (status=%s): %s", status, json)
        return json

    async def drop_index(self) -> None:
        url = f"{self._url}/{self.name}"
        async with aiohttp.ClientSession(timeout=self._timeout, json_serialize=orjson_dumps) as ses:
            try:
                resp = await ses.delete(url, headers=self._headers)
                json, status = await resp.json(), resp.status
                resp.raise_for_status()
            except Exception:
                msg = f"Error deleting index ({status=}): {json=}"
                logger.exception(msg)
                raise ElasticsearchException(msg) from None

        logger.info("Index deleted (status=%s): %s", status, json)

    async def healthcheck(self) -> bool:
        logger.debug("Checking elasticsearch is alive")
        url = f"{self._url}/_cluster/health"

        status, json = await self.__get(url)

        return json.get('status', '') in ('green', 'yellow')

    async def get(self, doc_id: UID) -> DOC:
        url = f"{self._url}/{self.name}/_doc/{doc_id}"

        return (await self.__get(url)).json

    async def add(self,
                  *,
                  doc: DOC,
                  doc_id: UID) -> DOC:
        """ Create or update the document """
        # TODO: bulk add
        url = f"{self._url}/{self.name}/_doc/{doc_id}"
        body = _serialize(doc)

        return (await self.__put(url, body)).json

    async def delete(self, doc_id: UID) -> DOC:
        url = f"{self._url}/{self.name}/_doc/{doc_id}"
        async with aiohttp.ClientSession(timeout=self._timeout, json_serialize=orjson_dumps) as ses:
            try:
                resp = await ses.delete(url, headers=self._headers)
                status, json = resp.status, await resp.json()
                resp.raise_for_status()
            except Exception:
                msg = f"Error deleting document ({status=}): {json=}"
                logger.exception(msg)
                raise ElasticsearchException(msg) from None

        return json

    async def match(self, query: str, field: str) -> DOC:
        url = f"{self._url}/{self.name}/_search"
        body = {
            "query": {
                "match": {
                    field: query,
                }
            }
        }

        return (await self.__put(url, body)).json

    async def multi_match(self, query: str) -> DOC:
        url = f"{self._url}/{self.name}/_search"
        body = {
            "query": {
                "multi_match": {
                    "query": query,
                    "fields": ["*"]
                }
            }
        }

        return (await self.__get(url, body)).json
