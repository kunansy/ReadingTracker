import base64
import datetime
from io import BytesIO
from typing import NamedTuple
from uuid import UUID

import matplotlib.pyplot as plt
import sqlalchemy.sql as sa

from tracker.common import models, database
from tracker.materials import db as materials_db
from tracker.reading_log import db as reading_log_db


class ReadingData(NamedTuple):
    counts: list[int]
    dates: list[datetime.date]


async def _get_graphic_data(*,
                            material_id: UUID,
                            last_days: int) -> ReadingData:
    dates, counts, total = [], [], 0
    _material_id = str(material_id)

    async for date, info in reading_log_db.data():
        if info.material_id != _material_id:
            continue
        total += info.count

        counts += [total]
        dates += [date]

    return ReadingData(
        counts[-last_days:],
        dates[-last_days:]
    )


async def get_read_material_titles() -> dict[UUID, str]:
    stmt = sa.select([models.Materials.c.material_id,
                      models.Materials.c.title])\
        .join(models.Statuses,
              models.Statuses.c.material_id == models.Materials.c.material_id)

    async with database.session() as ses:
        return {
            material_id: title
            for material_id, title in (await ses.execute(stmt)).all()
        }


async def create_reading_graphic(*,
                                 material_id: UUID,
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
    line.set_label(f'Overall {material.pages} pages')

    bar = ax.bar(data.dates, data.counts, width=1, edgecolor="white")
    ax.bar_label(bar)

    ax.set_title('Total pages read')
    ax.set_ylabel('Pages count')
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
            label=f"{str(remains)} pages remains"
        )

    ax.set(ylim=(0, material_pages + material_pages * .1))
    ax.legend()

    tmpbuf = BytesIO()
    fig.savefig(tmpbuf, format='png')
    return base64.b64encode(tmpbuf.getvalue()).decode('utf-8')
