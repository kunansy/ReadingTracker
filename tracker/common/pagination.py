import base64
import binascii
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Final

import sqlalchemy.sql as sa
from pydantic import AfterValidator, Field
from sqlalchemy import Text
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.common import database, sort_keys
from tracker.common.schemas import CustomBaseModel


DEFAULT_PAGE_SIZE: Final[int] = 20
MAX_PAGE_SIZE: Final[int] = 100
MAX_TOKEN_LENGTH: Final[int] = 1024
CURSOR_LABEL: Final[str] = "cursor"
COLLATION: Final[str] = "C"


class Order(StrEnum):
    ASC = "asc"
    DESC = "desc"


def encode_token(cursor: str) -> str:
    return base64.urlsafe_b64encode(cursor.encode()).decode()


def decode_token(token: str) -> str:
    msg = "next_token is not a valid page token"
    try:
        cursor = base64.b64decode(token, altchars=b"-_", validate=True).decode()
    except (binascii.Error, UnicodeError) as e:
        raise ValueError(msg) from e

    # Postgres rejects NUL in text parameters.
    if sort_keys.SEPARATOR not in cursor or "\x00" in cursor:
        raise ValueError(msg)
    return cursor


def _validate_token(token: str | None) -> str | None:
    if token is not None:
        decode_token(token)
    return token


class PageParams(CustomBaseModel):
    next_token: Annotated[
        str | None,
        Field(max_length=MAX_TOKEN_LENGTH),
        AfterValidator(_validate_token),
    ] = None
    page_size: Annotated[int, Field(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE
    # None means the default order of the listing.
    order: Order | None = None


@dataclass(frozen=True, slots=True)
class Page[T]:
    items: list[T]
    next_token: str | None
    total_count: int

    def with_items[U](self, items: list[U]) -> Page[U]:
        return Page(items=items, next_token=self.next_token, total_count=self.total_count)


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


def paginate(
    stmt: sa.Select,
    *,
    cursor_expr: sa.ColumnElement[str],
    params: PageParams,
    default_order: Order,
) -> sa.Select:
    """Rows from `next_token` inclusive, plus one extra row for the next token."""
    is_desc = (params.order or default_order) == Order.DESC
    stmt = stmt.add_columns(cursor_expr.label(CURSOR_LABEL)).order_by(None)
    if params.next_token is not None:
        start = decode_token(params.next_token)
        if is_desc:
            stmt = stmt.where(cursor_expr <= start)
        else:
            stmt = stmt.where(cursor_expr >= start)

    order = cursor_expr.desc() if is_desc else cursor_expr.asc()
    return stmt.order_by(order).limit(params.page_size + 1)


def split_page[T: Row](
    rows: Sequence[T],
    params: PageParams,
) -> tuple[Sequence[T], str | None]:
    if len(rows) <= params.page_size:
        return rows, None

    next_row = rows[params.page_size]
    return rows[: params.page_size], encode_token(getattr(next_row, CURSOR_LABEL))


async def count(ses: AsyncSession, stmt: sa.Select) -> int:
    count_stmt = sa.select(sa.func.count()).select_from(stmt.order_by(None).subquery())
    return await ses.scalar(count_stmt) or 0


async def fetch_page[T](
    stmt: sa.Select,
    *,
    cursor_expr: sa.ColumnElement[str],
    params: PageParams,
    default_order: Order,
    to_item: Callable[[Row], T],
) -> Page[T]:
    page_stmt = paginate(
        stmt,
        cursor_expr=cursor_expr,
        params=params,
        default_order=default_order,
    )

    async with database.session() as ses:
        rows = (await ses.execute(page_stmt)).all()
        total_count = await count(ses, stmt)

    page_rows, next_token = split_page(rows, params)
    return Page(
        items=[to_item(row) for row in page_rows],
        next_token=next_token,
        total_count=total_count,
    )
