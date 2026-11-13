import base64
import datetime
import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Any, Final, TypeGuard

import sqlalchemy.sql as sa
from pydantic import Field
from sqlalchemy import Text
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.common import database, sort_keys
from tracker.common.schemas import CustomBaseModel


DEFAULT_PAGE_SIZE: Final[int] = 20
MAX_PAGE_SIZE: Final[int] = 100
MAX_TOKEN_LENGTH: Final[int] = 4096
COLLATION: Final[str] = "C"
_CURSOR_COLUMN: Final[str] = "cursor"
_ORDER_PARAM: Final[str] = "order"
_MAX_ITEMS_PARAM: Final[str] = "max_items"
_CONTINUE_CURSOR_KEY: Final[str] = "cursor"
_PARAMS_KEY: Final[str] = "params"
_CONTINUE_FROM_KEY: Final[str] = "continue_from"
_INT4_PATTERN: Final = re.compile(r"[0-9]+")
_MAX_INT4: Final[int] = 2**31 - 1


class Order(StrEnum):
    ASC = "asc"
    DESC = "desc"


type TokenMap = dict[str, str]


def encode_next_token(params: TokenMap, continue_from: TokenMap) -> str:
    payload = {_PARAMS_KEY: params, _CONTINUE_FROM_KEY: continue_from}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _is_postgres_text(value: str) -> bool:
    # Postgres rejects NUL in text parameters, and asyncpg cannot encode lone surrogates.
    if "\x00" in value:
        return False
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _is_token_map(value: object) -> TypeGuard[TokenMap]:
    return isinstance(value, dict) and all(
        isinstance(key, str) and isinstance(val, str) and _is_postgres_text(val)
        for key, val in value.items()
    )


def decode_and_check_next_token(token: str, params: TokenMap) -> TokenMap:
    """Return the `continue_from` of the token issued for exactly these `params`."""
    try:
        payload = json.loads(base64.b64decode(token, altchars=b"-_", validate=True))
    except ValueError as e:
        raise database.InvalidNextTokenException("next_token is malformed") from e

    expected_keys = {_PARAMS_KEY, _CONTINUE_FROM_KEY}
    if not isinstance(payload, dict) or payload.keys() != expected_keys:
        raise database.InvalidNextTokenException("next_token is malformed")

    token_params, continue_from = payload[_PARAMS_KEY], payload[_CONTINUE_FROM_KEY]
    if not (_is_token_map(token_params) and _is_token_map(continue_from)):
        raise database.InvalidNextTokenException("next_token is malformed")
    if token_params != params:
        raise database.InvalidNextTokenException(
            "next_token does not match the request parameters",
        )
    if _CONTINUE_CURSOR_KEY not in continue_from:
        raise database.InvalidNextTokenException("next_token has no cursor")

    return continue_from


class PageParams(CustomBaseModel):
    next_token: Annotated[str | None, Field(max_length=MAX_TOKEN_LENGTH)] = None
    page_size: Annotated[int, Field(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE
    order: Order | None = None


def _param_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, set | frozenset):
        return ",".join(sorted(str(item) for item in value))
    return str(value)


@dataclass(frozen=True, slots=True)
class PageRequest:
    order: Order
    page_size: int
    params: TokenMap
    continue_from: TokenMap | None

    @property
    def cursor(self) -> str | None:
        return self.continue_from[_CONTINUE_CURSOR_KEY] if self.continue_from else None

    def next_token(self, cursor: str | None, **continue_from: str) -> str | None:
        if cursor is None:
            return None
        return encode_next_token(
            self.params,
            {_CONTINUE_CURSOR_KEY: cursor, **continue_from},
        )


def page_request(
    params: PageParams,
    *,
    default_order: Order,
    **filters: object,
) -> PageRequest:
    """Bind the page to the filters: a token is accepted only for the same ones."""
    order = params.order or default_order
    token_params = {
        _ORDER_PARAM: order.value,
        _MAX_ITEMS_PARAM: str(params.page_size),
        **{name: _param_value(value) for name, value in filters.items()},
    }
    continue_from = None
    if params.next_token is not None:
        continue_from = decode_and_check_next_token(params.next_token, token_params)

    return PageRequest(
        order=order,
        page_size=params.page_size,
        params=token_params,
        continue_from=continue_from,
    )


@dataclass(frozen=True, slots=True)
class Page[T]:
    items: list[T]
    next_token: str | None
    total_count: int

    def with_items[U](self, items: list[U]) -> Page[U]:
        return Page(
            items=items,
            next_token=self.next_token,
            total_count=self.total_count,
        )


class PageResponse(CustomBaseModel):
    next_token: str | None
    total_count: int


def datetime_part(column: sa.ColumnElement) -> sa.ColumnElement[str]:
    return sa.func.to_char(column, 'YYYY-MM-DD"T"HH24:MI:SS.US')


def date_part(column: sa.ColumnElement) -> sa.ColumnElement[str]:
    return sa.func.to_char(column, "YYYY-MM-DD")


def int_part(column: sa.ColumnElement) -> sa.ColumnElement[str]:
    return sa.func.lpad(sa.cast(column, Text), sort_keys.INT_WIDTH, "0")


def cursor(*parts: sa.ColumnElement) -> sa.ColumnElement[str]:
    expr: sa.ColumnElement = parts[0]
    for part in parts[1:]:
        expr = expr.concat(sort_keys.SEPARATOR).concat(part)
    return expr.collate(COLLATION)


@dataclass(frozen=True, slots=True)
class KeyPart:
    column: sa.ColumnElement[Any]
    text: sa.ColumnElement[str]
    parse: Callable[[str], object]


def date_key(column: sa.ColumnElement[Any]) -> KeyPart:
    return KeyPart(column, date_part(column), datetime.date.fromisoformat)


def datetime_key(column: sa.ColumnElement[Any]) -> KeyPart:
    return KeyPart(column, datetime_part(column), datetime.datetime.fromisoformat)


def _parse_int4(value: str) -> int:
    # int() would also take "+1", " 1" and "1_0"; the column is a 4-byte integer
    if not _INT4_PATTERN.fullmatch(value) or int(value) > _MAX_INT4:
        raise ValueError(f"Invalid integer cursor part {value!r}")
    return int(value)


def int_key(column: sa.ColumnElement[Any]) -> KeyPart:
    return KeyPart(column, int_part(column), _parse_int4)


def text_key(column: sa.ColumnElement[str]) -> KeyPart:
    return KeyPart(column, column, str)


@dataclass(frozen=True, slots=True)
class Keyset:
    """A cursor over several columns, compared as a row value of the columns.

    The token keeps the joined text of the parts, as `cursor()` builds it; the query
    compares and orders by the columns themselves, so a composite index serves the page.
    Every part but the last must not contain the separator.
    """

    parts: tuple[KeyPart, ...]

    @property
    def text(self) -> sa.ColumnElement[str]:
        return cursor(*(part.text for part in self.parts))

    def start(self, cursor_value: str) -> tuple[object, ...]:
        values = cursor_value.split(sort_keys.SEPARATOR, len(self.parts) - 1)
        if len(values) != len(self.parts):
            raise database.InvalidNextTokenException("next_token has no valid cursor")
        try:
            return tuple(
                part.parse(value) for part, value in zip(self.parts, values, strict=True)
            )
        except ValueError as e:
            raise database.InvalidNextTokenException(
                "next_token has no valid cursor",
            ) from e


def keyset(*parts: KeyPart) -> Keyset:
    return Keyset(parts)


def _paginate_keyset(stmt: sa.Select, *, key: Keyset, request: PageRequest) -> sa.Select:
    is_desc = request.order == Order.DESC
    stmt = stmt.add_columns(key.text.label(_CURSOR_COLUMN)).order_by(None)
    if (start := request.cursor) is not None:
        columns = sa.tuple_(*(part.column for part in key.parts))
        values = sa.tuple_(
            *(
                sa.bindparam(None, value, type_=part.column.type)
                for part, value in zip(key.parts, key.start(start), strict=True)
            ),
        )
        stmt = stmt.where(columns <= values if is_desc else columns >= values)

    order = [part.column.desc() if is_desc else part.column.asc() for part in key.parts]
    return stmt.order_by(*order).limit(request.page_size + 1)


def paginate(
    stmt: sa.Select,
    *,
    cursor_expr: sa.ColumnElement[str] | Keyset,
    request: PageRequest,
) -> sa.Select:
    """Rows from the cursor inclusive, plus one extra row for the next cursor."""
    if isinstance(cursor_expr, Keyset):
        return _paginate_keyset(stmt, key=cursor_expr, request=request)

    is_desc = request.order == Order.DESC
    stmt = stmt.add_columns(cursor_expr.label(_CURSOR_COLUMN)).order_by(None)
    if (start := request.cursor) is not None:
        if is_desc:
            stmt = stmt.where(cursor_expr <= start)
        else:
            stmt = stmt.where(cursor_expr >= start)

    order = cursor_expr.desc() if is_desc else cursor_expr.asc()
    return stmt.order_by(order).limit(request.page_size + 1)


def split_page[T: Row](
    rows: Sequence[T],
    page_size: int,
) -> tuple[Sequence[T], str | None]:
    """Split rows of `paginate` into the page and the next cursor."""
    if len(rows) <= page_size:
        return rows, None

    next_row = rows[page_size]
    return rows[:page_size], getattr(next_row, _CURSOR_COLUMN)


async def count(ses: AsyncSession, stmt: sa.Select) -> int:
    count_stmt = sa.select(sa.func.count()).select_from(stmt.order_by(None).subquery())
    return await ses.scalar(count_stmt) or 0


async def fetch_rows[T](
    stmt: sa.Select,
    *,
    cursor_expr: sa.ColumnElement[str] | Keyset,
    request: PageRequest,
    to_item: Callable[[Row], T],
) -> tuple[list[T], str | None, int]:
    """Items of the page, the cursor of the next page and the total count."""
    page_stmt = paginate(stmt, cursor_expr=cursor_expr, request=request)

    async with database.session() as ses:
        rows = (await ses.execute(page_stmt)).all()
        total_count = await count(ses, stmt)

    page_rows, next_cursor = split_page(rows, request.page_size)
    return [to_item(row) for row in page_rows], next_cursor, total_count


async def fetch_page[T](
    stmt: sa.Select,
    *,
    cursor_expr: sa.ColumnElement[str] | Keyset,
    request: PageRequest,
    to_item: Callable[[Row], T],
) -> Page[T]:
    items, next_cursor, total_count = await fetch_rows(
        stmt,
        cursor_expr=cursor_expr,
        request=request,
        to_item=to_item,
    )
    return Page(
        items=items,
        next_token=request.next_token(next_cursor),
        total_count=total_count,
    )
