#!/usr/bin/env python3
import datetime
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Iterable, Optional, Union

from tracker.common import database, settings
from tracker.common.log import logger


INDENT = 2


def fmt(value: Any) -> str:
    return ''


@dataclass(frozen=True)
class MaterialEstimate:
    material: database.Material
    will_be_started: datetime.date
    will_be_completed: datetime.date
    expected_duration: int

    def dict(self,
             *,
             exclude: Iterable[str] = None) -> dict:
        exclude = exclude or ()

        return {
            field: getattr(self, field, None)
            for field in self.__annotations__.keys()
            if field not in exclude
        }

    def __str__(self) -> str:
        return f"Material: «{self.material.title}»\n" \
               f"Pages: {self.material.pages}\n" \
               f"Will be started: {fmt(self.will_be_started)}\n" \
               f"Will be completed: {fmt(self.will_be_completed)}\n" \
               f"Expected duration: {time_span(self.expected_duration)}"


def to_datetime(date) -> Optional[datetime.date]:
    """
    :param date: str or date or datetime.

    :exception ValueError: if date format is wrong.
    :exception TypeError: if the param type is wrong.
    """
    if date is None:
        return

    if isinstance(date, str):
        try:
            date = datetime.datetime.strptime(date, settings.DATE_FORMAT)
            date = date.date()
        except ValueError as e:
            raise ValueError(f"Wrong str format\n{e}:{date}")
        else:
            return date
    elif isinstance(date, datetime.datetime):
        return date.date()
    elif isinstance(date, datetime.date):
        return date
    else:
        raise TypeError(f"Str or datetime expected, {type(date)} found")


def time_span(span: Union[timedelta, int]) -> str:
    days: int = span
    if isinstance(days, timedelta):
        days = days.days

    res = ''
    if years := days // 365:
        res += f"{years} years, "
    if month := days % 365 // 30:
        res += f"{month} months, "
    if days := days % 365 % 30:
        res += f"{days} days"

    return res


class Tracker:
    __slots__ = '__log',

    def __init__(self):
        self.__log = ...

    def statistics(self,
                   materials: list[database.MaterialStatus]
                   ) -> list[MaterialStatistics]:
        return [
            self.get_material_statistics(
                ms.material.material_id, material=ms.material, status=ms.status
            )
            for ms in materials
        ]

    def estimate(self) -> list[MaterialEstimate]:
        """ Get materials from queue with estimated time to read """
        a_day = timedelta(days=1)

        # start when all reading material will be completed
        start = self._end_of_reading()
        avg = self.log.average

        last_date = start + a_day
        forecasts = []

        for material in self.queue:
            expected_duration = round(material.pages / avg)
            expected_end = last_date + timedelta(days=expected_duration)

            forecast = MaterialEstimate(
                material=material,
                will_be_started=last_date,
                will_be_completed=expected_end,
                expected_duration=expected_duration
            )
            forecasts += [forecast]

            last_date = expected_end + a_day

        return forecasts

    def _end_of_reading(self) -> datetime.date:
        """ Calculate when all reading materials will be completed """
        remaining_days = sum(
            stat.remaining_days
            for stat in self.statistics(self.reading)
        )

        return database.today() + timedelta(days=remaining_days + 1)
