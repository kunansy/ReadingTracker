import base64
import datetime
from io import BytesIO
from typing import NamedTuple

import matplotlib.pyplot as plt
import sqlalchemy.sql as sa

from tracker.common import database
from tracker.models import models
from tracker.materials import db as materials_db
from tracker.reading_log import db as logs_db, statistics


class ReadingData(NamedTuple):
    counts: list[int]
    dates: list[datetime.date]


async def _get_graphic_data(*,
                            material_id: str,
                            last_days: int) -> ReadingData:
    dates, counts, total = [], [], 0

    async for date, info in logs_db.data():
        if info.material_id != material_id:
            continue
        total += info.count

        counts += [total]
        dates += [date]

    return ReadingData(
        counts[-last_days:],
        dates[-last_days:]
    )


async def get_read_material_titles() -> dict[str, str]:
    stmt = sa.select([models.Materials.c.material_id,
                      models.Materials.c.title])\
        .join(models.Statuses,
              models.Statuses.c.material_id == models.Materials.c.material_id)

    async with database.session() as ses:
        return {
            str(material_id): title
            for material_id, title in (await ses.execute(stmt)).all()
        }


async def get_material_reading_now() -> str | None:
    return await logs_db.get_material_reading_now()


async def create_reading_graphic(*,
                                 material_id: str,
                                 last_days: int = 14) -> str:
    if not (material := await materials_db.get_material(material_id=material_id)):
        raise ValueError(f"'{material_id=}' not found")

    data = await _get_graphic_data(
        material_id=material_id,
        last_days=last_days
    )
    total_pages_read = data.counts[-1]
    material_pages = material.pages

    fig, ax = plt.subplots(figsize=(12, 10))

    line = plt.axhline(y=material.pages, color='r', linestyle='-')
    line.set_label(f'Overall {material.pages} items')

    bar = ax.bar(data.dates, data.counts, width=1, edgecolor="white")
    ax.bar_label(bar)

    ax.set_title('Total items completed')
    ax.set_ylabel('Items count')
    ax.set_xlabel('Date')

    if (remains := material_pages - total_pages_read) > 0:
        last_rect = bar[-1]
        vline_x = last_rect.get_x() + last_rect.get_width() / 2

        ax.vlines(
            vline_x,
            ymin=last_rect.get_height(),
            ymax=material.pages,
            color='black',
            linestyles='solid',
            label=f"{remains} items remains"
        )

    ax.set(ylim=(0, material_pages + material_pages * .1))
    ax.legend()

    tmpbuf = BytesIO()
    fig.savefig(tmpbuf, format='png')
    return base64.b64encode(tmpbuf.getvalue()).decode('utf-8')


async def get_tracker_statistics() -> statistics.TrackerStatistics:
    return await statistics.get_tracker_statistics()
