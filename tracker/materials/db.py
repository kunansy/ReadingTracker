from datetime import datetime
from typing import Optional

import sqlalchemy.sql as sa
from sqlalchemy.engine import RowMapping

from tracker.common import database, models
from tracker.common.log import logger


async def get_materials(*,
                        materials_ids: Optional[list[int]] = None) -> list[models.Materials]:
    how_many = 'all'
    if materials_ids:
        how_many = len(materials_ids)

    logger.info("Getting %s materials", how_many)

    stmt = sa.select(models.Materials)
    if materials_ids:
        stmt = stmt.where(models.Materials.c.material_id.in_(materials_ids))

    async with database.session() as ses:
        return (await ses.execute(stmt)).all()


async def get_title(*,
                    material_id: int) -> str:
    logger.info("Getting title for material_id=%s", material_id)
    try:
        return (await get_materials(materials_ids=[material_id]))[0].title
    except IndexError:
        logger.warning(f"Material {material_id=} not found")
        return ''


async def does_material_exist(*,
                              material_id: int) -> bool:
    logger.debug("Whether material_id=%s exists", material_id)

    stmt = sa.select(models.Materials.c.material_id)\
        .where(models.Materials.c.material_id == material_id)

    async with database.session() as ses:
        return await ses.scalar(stmt) is not None


async def is_material_reading(*,
                              material_id: int) -> bool:
    logger.debug("Whether material_id=%s is reading",
                 material_id)

    stmt = sa.select(models.Materials.c.material_id)\
        .join(models.Statuses,
              models.Materials.c.material_id == models.Statuses.c.material_id)\
        .where(models.Statuses.c.begin != None)\
        .where(models.Statuses.c.end == None)\
        .where(models.Materials.c.material_id == material_id)

    async with database.session() as ses:
        return await ses.scalar(stmt) is not None


async def is_material_assigned(*,
                               material_id: int) -> bool:
    logger.debug("Whether material_id=%s reading or completed",
                 material_id)

    stmt = sa.select(models.Materials.c.material_id) \
        .join(models.Statuses,
              models.Materials.c.material_id == models.Statuses.c.material_id) \
        .where(models.Statuses.c.begin != None) \
        .where(models.Materials.c.material_id == material_id)

    async with database.session() as ses:
        return await ses.scalar(stmt) is not None


async def get_free_materials() -> list[models.Materials]:
    logger.debug("Getting free materials")

    # TODO: where not exists
    stmt = sa.select(models.Materials) \
        .join(models.Statuses,
              models.Materials.c.material_id == models.Statuses.c.material_id,
              isouter=True) \
        .where(models.Statuses.c.material_id == None)

    async with database.session() as ses:
        return (await ses.execute(stmt)).all()


async def get_reading_materials() -> list[RowMapping]:
    logger.debug("Getting reading materials")

    stmt = sa.select([models.Materials,
                      models.Statuses]) \
        .join(models.Statuses,
              models.Materials.c.material_id == models.Statuses.c.material_id) \
        .where(models.Statuses.c.end == None)

    async with database.session() as ses:
        return (await ses.execute(stmt)).mappings().all()


async def get_completed_materials() -> list[RowMapping]:
    logger.debug("Getting completed materials")

    stmt = sa.select([models.Materials,
                      models.Statuses]) \
        .join(models.Statuses,
              models.Materials.c.material_id == models.Statuses.c.material_id) \
        .where(models.Statuses.end != None)

    async with database.session() as ses:
        return (await ses.execute(stmt)).mappings().all()


async def get_status(*,
                     status_ids: Optional[list[int]] = None) -> list[models.Statuses]:
    how_many = 'all'
    if status_ids:
        how_many = len(status_ids)

    logger.debug("Getting %s statuses", how_many)

    stmt = sa.select(models.Statuses)
    if status_ids:
        stmt = stmt.where(models.Statuses.c.status_id.in_(status_ids))

    async with database.session() as ses:
        return (await ses.execute(stmt)).all()


async def get_material_status(*,
                              material_id: int) -> models.Statuses:
    logger.debug("Getting status for material_id=%s",
                 material_id)

    stmt = sa.select(models.Statuses)\
        .where(models.Statuses.c.material_id == material_id)

    async with database.session() as ses:
        if (material := (await ses.execute(stmt)).first()) is None:
            raise ValueError("Status for material_id=%s not found",
                             material_id)
        return material


async def add_material(*,
                       title: str,
                       authors: str,
                       pages: int,
                       tags: str) -> None:
    logger.debug("Adding material")

    values = {
        "title": title,
        "authors": authors,
        "pages": pages,
        "tags": tags
    }
    stmt = models.Materials\
        .insert().values(values)\
        .returning(models.Materials.c.material_id)

    async with database.session() as ses:
        material = await ses.execute(stmt)

    logger.debug("Material_id=%s added", material.material_id)


async def start_material(*,
                         material_id: int,
                         start_date: Optional[datetime.date] = None) -> None:
    start_date = start_date or database.today()
    logger.debug("Starting material_id=%s at %s",
                 material_id, start_date)

    if start_date > database.today():
        raise ValueError("Start date must be less than today")

    values = {
        "material_id": material_id,
        "start_date": start_date
    }
    stmt = models.Statuses\
        .insert().values(values)

    async with database.session() as ses:
        await ses.execute(stmt)

    logger.debug("Material material_id=%s started at %s",
                 material_id, start_date)


async def complete_material(*,
                            material_id: int,
                            completion_date: Optional[datetime.date] = None) -> None:
    completion_date = completion_date or database.today()
    logger.debug("Completing material_id=%s at %s",
                 material_id, completion_date)

    get_status_stmt = sa.select(models.Statuses)\
        .where(models.Statuses.c.material_id == material_id)
    update_status_stmt = models.Statuses\
        .update().values(end=completion_date)\
        .where(models.Statuses.c.material_id == material_id)

    async with database.session() as ses:
        status = (await ses.execute(get_status_stmt)).mappings().first()
        if status is None:
            raise ValueError("Material_id=%s not assigned", material_id)

        if status.end is not None:
            raise ValueError("Material_id=%s even completed", material_id)
        if status.begin > completion_date:
            raise ValueError("Begin cannot be more than end")

        await ses.execute(update_status_stmt)

    logger.debug("Material_id=%s completed at %s",
                 material_id, completion_date)
