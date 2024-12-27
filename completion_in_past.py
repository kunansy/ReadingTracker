"""The script adds completion history."""

import asyncio
import datetime
from typing import Any, Self
from uuid import UUID

import sqlalchemy.sql as sa
import uuid6
from pydantic import PositiveInt, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.common import database, logger
from tracker.common.schemas import CustomBaseModel
from tracker.models import models


class Completion(CustomBaseModel):
    title: str
    started_at: datetime.date
    completed_at: datetime.date
    pages: list[PositiveInt]

    @model_validator(mode="after")
    def validate_dates_relation(self) -> Self:
        if self.started_at > self.completed_at:
            raise ValueError("Finish date must be greater than start")

        return self

    @model_validator(mode="after")
    def validate_pages_size(self) -> Self:
        duration = (self.completed_at - self.started_at).days + 1
        if len(self.pages) != duration:
            raise ValueError("Pages list size don't mathc with the duration")

        return self

    @model_validator(mode="before")
    @classmethod
    def parse_pages(cls, data: dict[str, Any]) -> dict[str, Any]:
        pages = [int(page) for page in data["pages"].split()]
        data["pages"] = pages

        return data


def fill_completion() -> Completion:
    fields: dict = {}
    for name, annotation in Completion.model_fields.items():
        field = input(f"Enter '{name}' of type {annotation.annotation}: ")
        fields[name] = field

    return Completion(**fields)


def _build_insert_statuses_query(completion: Completion, material_id: UUID | str) -> str:
    return f"""
        INSERT INTO
            statuses (status_id, material_id, started_at, completed_at)
        VALUES
            ('{uuid6.uuid7()}', '{material_id}',
            '{completion.started_at}', '{completion.completed_at}')
    """


def _build_insert_reading_log(completion: Completion, material_id: UUID | str) -> str:
    start = completion.started_at
    td = datetime.timedelta
    values = ", ".join(
        f"('{uuid6.uuid7()}', '{material_id}', '{start + td(days=num)}', {count})"
        for (num, count) in enumerate(completion.pages)
    )
    return f"""
        INSERT INTO
            reading_log (log_id, material_id, date, count)
        VALUES
            {values}
    """


async def _insert(transaction: AsyncSession, query: str) -> None:
    if not transaction.in_transaction():
        raise ValueError("Transaction not began")

    await transaction.execute(sa.text(query))


async def _check_insertion(
    transaction: AsyncSession,
    completion: Completion,
    material_id: UUID | str,
) -> bool:
    status_stmt = (
        sa.select(
            models.Statuses.c.started_at,
            models.Statuses.c.completed_at,
            models.Statuses.c.material_id,
        )
        .select_from(models.Statuses)
        .where(models.Statuses.c.material_id == str(material_id))
    )
    reading_log_stmt = (
        sa.select(
            models.ReadingLog.c.date,
            models.ReadingLog.c.count,
            models.ReadingLog.c.material_id,
        )
        .select_from(models.ReadingLog)
        .where(models.ReadingLog.c.material_id == str(material_id))
    )

    status = (await transaction.execute(status_stmt)).one()
    started_at, completed_at, smaterial_id = status
    if (
        started_at.date() != completion.started_at
        or completed_at.date() != completion.completed_at
        or smaterial_id != material_id
    ):
        logger.error("Status not fit: %r != %r", status, completion)
        return False

    reading_logs = (await transaction.execute(reading_log_stmt)).all()
    start = completion.started_at
    for num, count in enumerate(completion.pages):
        date, rcount, rmaterial_id = reading_logs[num]

        if (
            date != start + datetime.timedelta(days=num)
            or count != rcount
            or material_id != rmaterial_id
        ):
            logger.error("Reading log no fit: %r != %r", reading_logs[num], completion)
            return False

    return True


async def _get_material_id(transaction: AsyncSession, title: str) -> UUID:
    stmt = sa.select(models.Materials.c.material_id).where(
        models.Materials.c.title == title,
    )

    if material_id := await transaction.scalar(stmt):
        return material_id
    raise ValueError(f"Material {title=!r} not found")


async def insert_completions(completions: list[Completion]) -> None:
    if not completions:
        return

    async with database.transaction() as t:
        for completion in completions:
            material_id = await _get_material_id(t, completion.title)

            insert_statuses_query = _build_insert_statuses_query(completion, material_id)
            insert_reading_log = _build_insert_reading_log(completion, material_id)

            logger.debug(insert_statuses_query)
            logger.debug(insert_reading_log)

            await _insert(t, insert_statuses_query)
            await _insert(t, insert_reading_log)

            if not await _check_insertion(t, completion, material_id):
                logger.error("Check not passed, rollback")
                await t.rollback()
                return


async def main() -> None:
    completions_count = int(input("Enter completions count: "))

    completions = [fill_completion() for _ in range(completions_count)]
    await insert_completions(completions)

    logger.info("Total %s statuses added", len(completions))


if __name__ == "__main__":
    asyncio.run(main())
