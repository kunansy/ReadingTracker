"""Materials in each reading state, created through the public db API."""

import datetime
import uuid

from tracker.common import database
from tracker.materials import db
from tracker.models import enums


async def insert_material() -> uuid.UUID:
    return await db.insert_material(
        title=f"Test material {uuid.uuid4()}",
        authors="Author",
        pages=10,
        material_type=enums.MaterialTypesEnum.book,
        tags=None,
        link=None,
    )


async def start_material(days_ago: int = 2) -> tuple[uuid.UUID, datetime.date]:
    material_id = await insert_material()
    started_at = database.utcnow().date() - datetime.timedelta(days=days_ago)
    await db.start_material(material_id=material_id, started_at=started_at)
    return material_id, started_at


async def complete_material(
    *,
    started_days_ago: int = 2,
    completed_days_ago: int = 1,
) -> tuple[uuid.UUID, datetime.date]:
    material_id, _ = await start_material(days_ago=started_days_ago)
    completed_at = database.utcnow().date() - datetime.timedelta(days=completed_days_ago)
    await db.complete_material(material_id=material_id, completed_at=completed_at)
    return material_id, completed_at
