import datetime
from typing import NamedTuple
from uuid import UUID

import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import numpy as np
import sqlalchemy.sql as sa

from tracker.common import database, settings
from tracker.materials import db as materials_db
from tracker.models import enums, models
from tracker.reading_log import (
    db as logs_db,
)
from tracker.system import figures


class ReadingData(NamedTuple):
    counts: list[int]
    dates: list[datetime.date]


async def _get_graphic_data(*, material_id: UUID, last_days: int) -> ReadingData:
    dates, counts, total = [], [], 0

    async for date, info in logs_db.data():
        if info.material_id != material_id:
            continue
        total += info.count

        counts.append(total)
        dates.append(date)

    return ReadingData(counts[-last_days:], dates[-last_days:])


def _set_plot_style() -> None:
    if datetime.datetime.now(tz=datetime.UTC).time() >= settings.EX_DARKMODE_ENABLE:
        plt.style.use("dark_background")
    else:
        plt.style.use("default")


async def create_reading_graphic(*, material_id: UUID, last_days: int) -> str:
    material = await materials_db.get_material_api(material_id=material_id)

    data = await _get_graphic_data(material_id=material_id, last_days=last_days)
    total_pages_read = data.counts[-1] if data.counts else 0
    material_pages = material.pages

    _set_plot_style()
    fig, ax = figures.create_figure()

    line = ax.axhline(y=material.pages, color="r", linestyle="-")
    line.set_label(f"Overall {material.pages} items")

    bar = ax.bar(data.dates, data.counts, width=1, edgecolor="white")  # type: ignore[arg-type]
    ax.bar_label(bar)

    ax.set_title("Total items completed")
    ax.set_ylabel("Items count")
    ax.set_xlabel("Date")

    if (remains := material_pages - total_pages_read) > 0 and data.counts:
        last_rect = bar[-1]
        vline_x = last_rect.get_x() + last_rect.get_width() / 2

        ax.vlines(
            vline_x,
            ymin=last_rect.get_height(),
            ymax=material.pages,
            color="black",
            linestyles="solid",
            label=f"{remains} items remains",
        )

    ax.set(ylim=(0, material_pages + material_pages * 0.1))
    ax.legend()

    return figures.render_svg_base64(fig)


async def _calculate_outline_percentage() -> dict[
    enums.MaterialTypesEnum,
    dict[bool, int],
]:
    stmt = (
        sa.select(
            models.Materials.c.material_type,
            models.Materials.c.is_outlined,
            sa.func.count(1),
        )
        .where(models.MATERIAL_IS_COMPLETED)
        .group_by(models.Materials.c.material_type, models.Materials.c.is_outlined)
    )

    outline_percentage: dict[enums.MaterialTypesEnum, dict[bool, int]] = {}
    async with database.session() as ses:
        for material_type, is_outlined, count in (await ses.execute(stmt)).all():
            outline_percentage.setdefault(material_type, {}).setdefault(
                is_outlined,
                count,
            )

    return outline_percentage


async def create_outline_percentage_graphic() -> str:
    stat = await _calculate_outline_percentage()
    material_types = sorted(enums.MaterialTypesEnum)
    species = [material_type.value for material_type in material_types]

    outlined, not_outlined = [], []
    for material_type in material_types:
        counts = stat.get(material_type, {})
        outlined_count, not_outlined_count = counts.get(True, 0), counts.get(False, 0)
        total = outlined_count + not_outlined_count

        percent = round(outlined_count / total, 4) * 100 if total else 0
        outlined.append(percent)
        not_outlined.append(100 - percent if total else 0)

    width = 0.6

    _set_plot_style()
    fig, ax = figures.create_figure()
    bottom = np.zeros(len(species))

    for label, percents in {"outlined": outlined, "not_outlined": not_outlined}.items():
        p = ax.bar(species, percents, width, label=label, bottom=bottom)
        bottom += percents

        ax.bar_label(p, label_type="center")

    ax.set_title("Outline percentage")
    ax.yaxis.set_major_formatter(mtick.PercentFormatter())
    ax.legend()

    return figures.render_svg_base64(fig)
