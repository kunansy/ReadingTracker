import base64
from io import BytesIO

import matplotlib.pyplot as plt

from tracker.common.log import logger
from tracker.trends import db


def _create_graphic(*,
                    statistics: db.WeekStatistics,
                    title: str = 'Total items completed') -> str:
    logger.debug("Creating graphic started")

    fig, ax = plt.subplots(figsize=(12, 10))
    bar = ax.barh(statistics.days, statistics.values, edgecolor="white")
    ax.bar_label(bar)

    ax.set_title(title)
    ax.set_xlabel('Items count')
    ax.set_ylabel('Date')
    plt.gca().invert_yaxis()

    tmpbuf = BytesIO()
    fig.savefig(tmpbuf, format='png')

    image = base64.b64encode(tmpbuf.getvalue()).decode('utf-8')

    logger.debug("Creating graphic completed")
    return image


async def create_reading_graphic() -> str:
    logger.info("Creating reading graphic")

    statistics = await db.get_week_reading_statistics()
    return _create_graphic(
        statistics=statistics,
        title='Total pages read'
    )


async def create_notes_graphic() -> str:
    logger.info("Creating notes graphic")

    statistics = await db.get_week_notes_statistics()
    return _create_graphic(
        statistics=statistics,
        title='Total notes inserted'
    )
