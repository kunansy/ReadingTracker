#!/usr/bin/env python3
import copy
import datetime
import logging
from dataclasses import dataclass
from datetime import timedelta
from itertools import groupby
from pathlib import Path
from typing import Union, Optional, Iterator, Iterable
from src.db_api import MaterialNotFound, MaterialNotAssigned
from src.db_api import MaterialEvenCompleted, WrongDate, BaseDBError

import ujson

import src.db_api as db


DATA_FOLDER = Path('data')
PAGES_PER_DAY = 50
INDENT = 2

DATE_FORMAT = '%d-%m-%Y'

logger = logging.getLogger('ReadingTracker')


class BaseTrackerError(Exception):
    pass


class LoadingLogError(BaseTrackerError):
    pass


class ReadingLogIsEmpty(BaseTrackerError):
    pass


@dataclass
class MinMax:
    date: datetime.date
    count: int
    material_id: int
    material_title: Optional[str] = None

    def dict(self,
             *,
             exclude: Iterable[str] = None) -> dict:
        exclude = exclude or ()

        return {
            field: getattr(self, field, None)
            for field in self.__annotations__.keys()
            if field not in exclude
        }

    def __repr__(self) -> str:
        data = ', '.join(
            f"{field}={value}"
            for field, value in self.dict().items()
        )
        return f"{self.__class__.__name__}({data})"

    def __str__(self) -> str:
        date = fmt(self.date)

        if material_title := self.material_title:
            material = f"Title: «{material_title}»"
        else:
            material = f"Material id: {self.material_id}"

        return f"Date: {date}\n" \
               f"Count: {self.count} pages\n" \
               f"{material}"


@dataclass
class LogRecord:
    count: int
    material_id: int
    material_title: Optional[str] = None

    def dict(self) -> dict:
        return {
            field: getattr(self, field, None)
            for field in self.__annotations__.keys()
        }

    def __repr__(self) -> str:
        data = ', '.join(
            f"{field}={value}"
            for field, value in self.dict().items()
        )

        return f"{self.__class__.__name__}({data})"
    
    def __str__(self) -> str:
        if title := self.material_title:
            title = f"\nTitle: «{title}»"
        else:
            title = ''

        return f"Count: {self.count}\n" \
               f"Material id: {self.material_id}" \
               f"{title}"


@dataclass
class LogStatistics:
    start_date: datetime.date
    stop_date: datetime.date
    duration: int
    # amount of empty days
    lost_time: int
    average: int
    total_pages_read: int
    # would be total if there were no empty days
    would_be_total: int
    min: MinMax
    max: MinMax
    median: int

    def dict(self) -> dict:
        return {
            field: getattr(self, field, None)
            for field in self.__annotations__.keys()
        }

    def __repr__(self) -> str:
        data = ',\n'.join(
            f"{field}={value}"
            for field, value in self.dict().items()
        )
        return f"{self.__class__.__name__}({data})"

    def __str__(self) -> str:
        min_ = '\n'.join(
            f"\t{field.capitalize()}: {value}"
            for field, value in self.min.dict(exclude={'material_id'}).items()
        )

        max_ = '\n'.join(
            f"\t{field.capitalize()}: {value}"
            for field, value in self.max.dict(exclude={'material_id'}).items()
        )

        return f"Start: {fmt(self.start_date)}\n" \
               f"Stop: {fmt(self.stop_date)}\n" \
               f"Duration: {time_span(self.duration)}\n" \
               f"Lost time: {time_span(self.lost_time)}\n" \
               f"Average: {self.average} pages per day\n" \
               f"Total pages read: {self.total_pages_read}\n" \
               f"Would be total: {self.would_be_total}\n" \
               f"Min:\n{min_}\n" \
               f"Max:\n{max_}\n" \
               f"Median: {self.median} pages"


@dataclass
class MaterialStatistics:
    material: db.Material
    started: datetime.date
    duration: int
    lost_time: int
    total: int
    min: MinMax
    max: MinMax
    average: int
    remaining_pages: Optional[int] = None
    remaining_days: Optional[int] = None
    completed: Optional[datetime.date] = None
    # date when the material would be completed
    # according to average read pages count
    would_be_completed: Optional[datetime.date] = None

    def dict(self,
             *,
             exclude: Iterable[str] = None) -> dict:
        exclude = exclude or ()

        return {
            field: getattr(self, field, None)
            for field in self.__annotations__.keys()
            if field not in exclude
        }

    def __repr__(self) -> str:
        data = ', '.join(
            f"{field}={value}"
            for field, value in self.dict().items()
        )

        return f"{self.__class__.__name__}({data})"

    def __str__(self) -> str:
        if completed := self.completed:
            completed = f"Completed at: {fmt(completed)}\n"
        else:
            completed = ''

        if would_be_completed := self.would_be_completed:
            would_be_completed = f"\nWould be completed at: " \
                                 f"{fmt(would_be_completed)}"
        else:
            would_be_completed = ''
        remaining_pages = (f"Remaining pages: {self.remaining_pages}\n" *
                           bool(self.remaining_pages))
        remaining_days = (f"Remaining days: {self.remaining_days}\n" *
                          bool(self.remaining_days))

        min_ = self.min
        min_ = f"\tDate: {fmt(min_.date)}\n" \
               f"\tCount: {min_.count} pages"

        max_ = self.max
        max_ = f"\tDate: {fmt(max_.date)}\n" \
               f"\tCount: {max_.count} pages"

        return f"Material: «{self.material.title}»\n" \
               f"Pages: {self.material.pages}\n" \
               f"Started at: {fmt(self.started)}\n" \
               f"{completed}" \
               f"Duration: {time_span(self.duration)}\n" \
               f"Lost time: {time_span(self.lost_time)}\n" \
               f"Total: {self.total} pages\n" \
               f"{remaining_pages}" \
               f"{remaining_days}" \
               f"Min:\n{min_}\n" \
               f"Max:\n{max_}\n" \
               f"Average: {self.average} pages per day" \
               f"{would_be_completed}"


@dataclass
class TrackerStatistics:
    pass


def today() -> datetime.date:
    return datetime.date.today()


def yesterday() -> datetime.date:
    return today() - timedelta(days=1)


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
            date = datetime.datetime.strptime(date, DATE_FORMAT)
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
    if isinstance(span, timedelta):
        days = timedelta.days
    else:
        days = span

    res = ''
    if years := days // 365:
        res += f"{years} years, "
    if month := days % 365 // 30:
        res += f"{month} months, "
    if days := days % 365 % 30:
        res += f"{days} days"

    return res


def fmt(date: datetime.date) -> str:
    return date.strftime(DATE_FORMAT)


class Log:
    __slots__ = '__log'

    LOG_PATH = DATA_FOLDER / 'log.json'

    def __init__(self,
                 *,
                 full_info: bool = False) -> None:
        """
        :param full_info: if True get titles to all materials.
         !!! there will be more queries to the database !!!
        """
        try:
            self.__log = self._get_log(full_info=full_info)
        except Exception as e:
            logger.error(f"When load the log: {e}")
            raise LoadingLogError(e)

    @property
    def log(self) -> dict[datetime.date, LogRecord]:
        return self.__log

    @property
    def path(self) -> Path:
        return self.LOG_PATH

    @property
    def start(self) -> Optional[datetime.date]:
        """ Get the date of the first logged day
        (if there is, None otherwise).
        """
        try:
            return list(self.log.keys())[0]
        except IndexError:
            pass

    @property
    def stop(self) -> Optional[datetime.date]:
        if self.start is not None:
            return list(self.keys())[-1]

    @property
    def reading_material(self) -> int:
        """ Get id of the reading material. """
        try:
            return list(self.log.values())[-1].material_id
        except IndexError:
            msg = "Reading log is empty, no materials reading"
            logger.warning(msg)
            raise ReadingLogIsEmpty(msg)

    def _get_log(self,
                 *,
                 full_info: bool = False) -> dict[datetime.date, LogRecord]:
        """
        Get log from JSON file and parse it.
        Convert keys to datetime.date, values to LogRecord.

        :param full_info: if True get titles to all materials.
         !!! there will be more queries to the database !!!

        :return: dict with the format.
        """
        with self.path.open(encoding='utf-8') as f:
            log = ujson.load(f)

        res = {}
        for date, info in log.items():
            date = to_datetime(date)
            record = LogRecord(**info)

            if full_info:
                record.material_title = db.get_title(record.material_id)

            res[date] = record
        return res

    def _set_log(self,
                 date: datetime.date,
                 count: int,
                 material_id: int = None) -> None:
        """
        Set reading log for the day.

        :param date: date of log.
        :param count: count of read pages.
        :param material_id: id of the learned material,
         by default id of the last material if exists.

        :exception ValueError: if count <= 0, the date
         is more than today, the date even exists in
         log, 'material_id' is None and log is empty.
        """
        if count <= 0:
            raise ValueError(f"Count must be > 0, but 0 <= {count}")
        if date <= self.stop:
            raise ValueError("The date must be less than today,"
                             f"but {date=} > {self.stop=}")
        if date in self.__log:
            raise ValueError(f"The {date=} even exists in the log")
        if material_id is None and len(self.log) == 0:
            raise ValueError(f"{material_id=} and log dict is empty")

        record = LogRecord(
            material_id=material_id or self.reading_material,
            count=count,
            material_title=db.get_title(material_id=material_id)
        )
        self.__log[date] = record

        self.__log = dict(sorted(self.log.items(), key=lambda i: i[0]))

    def set_today_log(self,
                      count: int,
                      material_id: int = None) -> None:
        """
        Set today's reading log.

        :param count: count of pages read today.
        :param material_id: id of learned material.
         The last learned material_id by default.
        """
        try:
            self._set_log(today(), count, material_id)
        except ValueError:
            logger.exception(f"Cannot set today's log with "
                             f"{count=}, {material_id=}")

    def set_yesterday_log(self,
                          count: int,
                          material_id: int = None) -> None:
        """
        Set yesterday's reading log.

        :param count: count of pages read yesterday.
        :param material_id: id of learned material.
         The last learned material_id by default.
        """
        try:
            self._set_log(yesterday(), count, material_id)
        except ValueError:
            logger.exception(f"Cannot set yesterday's log with "
                             f"{count=}, {material_id=}")

    def dump(self) -> None:
        """ Dump log to the file. """

        data = {
            fmt(date): info
            for date, info in self.log.items()
        }

        with self.path.open('w', encoding='utf-8') as f:
            ujson.dump(data, f, indent=INDENT)

    @property
    def total(self) -> int:
        """ Get total count of read pages """
        return sum(
            info.count
            for info in self.values()
        )

    @property
    def duration(self) -> int:
        """ Get duration of log """
        return (self.stop - self.start).days + 1

    @property
    def empty_days(self) -> int:
        return self.duration - len(self.log)

    @property
    def average(self) -> int:
        """ get the average count of pages read per day """
        try:
            return self.total // self.duration
        except ZeroDivisionError:
            return 1

    @property
    def min(self) -> MinMax:
        date, info = min(
            [(date, info) for date, info in self.items()],
            key=lambda item: item[1].count
        )
        return MinMax(
            date=date,
            **info.dict()
        )

    @property
    def max(self) -> MinMax:
        date, info = max(
            [(date, info) for date, info in self.items()],
            key=lambda item: item[1].count
        )

        return MinMax(
            date=date,
            **info.dict()
        )

    @property
    def median(self) -> int:
        counts = sorted(
            info.count
            for info in self.values()
        )

        if (middle := len(counts) // 2) % 2 == 0:
            return (counts[middle] + counts[middle + 1]) // 2
        return counts[middle]

    @property
    def would_be_total(self) -> int:
        """
        Get count of pages would be total
        if there were no empty days.
        """
        return self.total + self.average * self.empty_days

    def values(self):
        return self.log.values()

    def keys(self):
        return self.log.keys()

    def items(self):
        return self.log.items()

    def data(self) -> Iterator[tuple[datetime.date, LogRecord]]:
        """ Get pairs: date, info of all days from start to stop.
        The function is expected to make graphics.

        If the day is empty, material_id is supposed
        as the material_id of the last not empty day.
        """
        step = timedelta(days=1)
        iter_ = self.start
        last_material_id = -1

        while iter_ <= self.stop:
            info = self.log.get(iter_)
            info = info or LogRecord(material_id=last_material_id, count=0)

            if (material_id := info.material_id) != last_material_id:
                last_material_id = material_id

            yield iter_, info
            iter_ += step

    def m_duration(self,
                   material_id: int) -> int:
        """ Calculate how many days the material was being reading """
        return sum(
            1
            for _, info in self.data()
            if info.material_id == material_id
        )

    def m_total(self,
                material_id: int) -> int:
        """ Calculate how many pages of the material even read """
        return sum(
            info.count
            for info in self.values()
            if info.material_id == material_id
        )

    def m_empty_days(self,
                     material_id: int) -> int:
        """ How many days was lost reading the material """
        return sum(
            1
            for _, info in self.data()
            if info.material_id == material_id and info.count == 0
        )

    def m_min(self,
              material_id: int) -> MinMax:
        sample = [
            (date, info)
            for date, info in self.items()
            if info.material_id == material_id
        ]
        date, info = min(
            sample,
            key=lambda item: item[1].count
        )
        return MinMax(
            date=date,
            **info.dict()
        )

    def m_max(self,
              material_id: int) -> MinMax:
        sample = [
            (date, info)
            for date, info in self.items()
            if info.material_id == material_id
        ]
        date, info = max(
            sample,
            key=lambda item: item[1].count
        )
        return MinMax(
            date=date,
            **info.dict()
        )

    def m_average(self,
                  material_id: int) -> int:
        try:
            return (self.m_total(material_id) //
                    self.m_duration(material_id))
        except ZeroDivisionError:
            return 1

    def dates(self) -> list[datetime.date]:
        return [
            date
            for date, _ in self.data()
        ]

    def counts(self) -> list[int]:
        return [
            info.count
            for _, info in self.data()
        ]

    def copy(self):
        new_log = self
        new_log.__log = copy.deepcopy(self.log)

        return new_log

    @property
    def statistics(self) -> LogStatistics:
        return LogStatistics(
            start_date=self.start,
            stop_date=self.stop,
            duration=self.duration,
            lost_time=self.empty_days,
            average=self.average,
            total_pages_read=self.total,
            would_be_total=self.would_be_total,
            min=self.min,
            max=self.max,
            median=self.median
        )

    def __getitem__(self,
                    date: Union[datetime.date, str, slice]):
        """
        Get log record by date (datetime.date or str)
        of by slice of dates.

        If slice get new Log object with [start; stop).
        """
        if not isinstance(date, (datetime.date, slice, str)):
            raise TypeError(f"Date or slice of dates expected, "
                            f"but {type(date)} found")

        if isinstance(date, (datetime.date, str)):
            return self.log[to_datetime(date)]

        start, stop, step = date.start, date.stop, date.step

        assert start is None or isinstance(start, (datetime.date, str))
        assert stop is None or isinstance(stop, (datetime.date, str))
        assert step is None or isinstance(step, int)

        assert not (start and stop) or start <= stop

        start = to_datetime(start or self.start)
        stop = to_datetime(stop or self.stop)

        step = timedelta(days=(step or 1))

        iter_ = start
        new_log_content = {}
        new_log = self.copy()

        while iter_ <= stop:
            if start <= iter_ <= stop:
                if iter_ in new_log.log:
                    new_log_content[iter_] = new_log.log[iter_]
            else:
                break
            iter_ += step
        new_log.__log = new_log_content
        return new_log

    def __len__(self) -> int:
        return len(self.log)

    def __str__(self) -> str:
        """
        If there are the same material on several days,
        add title of it in the first day and '...' to next
        ones instead of printing out the title every time.
        """
        res, is_first = '', True
        last_material_id, last_material_title = -1, ''
        new_line = '\n'

        for date, info in self.log.items():
            if (material_id := info.material_id) != last_material_id:
                last_material_id = material_id
                last_material_title = (info.material_title or
                                       f"«{db.get_title(material_id)}»")
            else:
                last_material_title = '...'

            item = f"{new_line * (not is_first)}{fmt(date)}: " \
                   f"{info.count}, {last_material_title}"

            is_first = False
            res = f"{res}{item}"

        return res

    def __repr__(self) -> str:
        log_records = ', '.join(
            f"{date}: {info}"
            for date, info in self.log.items()
        )
        return f"{self.__class__.__name__}({log_records})"


class Tracker:
    __slots__ = '__log',

    def __init__(self,
                 log: Log) -> None:
        self.__log = log

    @property
    def queue(self) -> list[db.Material]:
        """
        Get list of uncompleted materials:
        assigned but not completed and not assigned too
        """
        return db.get_free_materials()

    @property
    def processed(self) -> db.MATERIAL_STATUS:
        """ Get list of completed Materials. """
        return db.get_completed_materials()

    @property
    def reading(self) -> db.MATERIAL_STATUS:
        """ Get reading materials and their statuses """
        return db.get_reading_materials()

    @property
    def log(self) -> Log:
        return self.__log

    @property
    def notes(self) -> list[db.Note]:
        return db.get_notes()

    def get_material_statistic(self,
                               material_id: int,
                               *,
                               material: db.Material = None,
                               status: db.Status = None) -> MaterialStatistics:
        """ Calculate statistics for reading or completed material """
        material = material or self.get_material(material_id)
        status = status or self.get_status(material_id)

        assert material.material_id == status.material_id == material_id

        avg = self.log.m_average(material_id)
        total = self.log.m_total(material_id)

        if status.end is None:
            remaining_pages = material.pages - total
            remaining_days = round(remaining_pages // avg)
            would_be_completed = today() + timedelta(days=remaining_days)
        else:
            would_be_completed = remaining_days = remaining_pages = None

        return MaterialStatistics(
            material=material,
            started=status.begin,
            completed=status.end,
            duration=self.log.m_duration(material_id),
            lost_time=self.log.m_empty_days(material_id),
            total=total,
            min=self.log.m_min(material_id),
            max=self.log.m_max(material_id),
            average=avg,
            remaining_pages=remaining_pages,
            remaining_days=remaining_days,
            would_be_completed=would_be_completed
        )

    def _queue(self) -> str:
        """
        The func if expected to make strings like that:

        id=5 «Современные ОС», pages: 1120
        will be read from 12-12-2020 to 15-03-2021 in 93 days

        They should be divided by double \n symbol.
        """
        last_date = self.log.start
        average = self.log.average

        res, is_first = '', True

        for material in self.queue:
            if not is_first:
                res = f"{res}\n\n"
            is_first = False

            expected_duration = material.pages // average
            expected_end = last_date + timedelta(days=expected_duration)

            res += f"id={material.material_id} «{material.title}», " \
                   f"pages: {material.pages}\nWill be read " \
                   f"from {fmt(last_date)} to {fmt(expected_end)} " \
                   f"in {expected_duration} days"

            last_date = expected_end + timedelta(days=1)
        return res

    def _processed(self) -> str:
        """
        The func if expected to make strings like that:

        id=3 «Эйнштейн гуляет по Луне», pages: 384
        From 17-03-2021 to 20-03-2021 in 3 days
        average = 96 pages per day

        They should be divided by double \n symbol.
        """
        if not (materials := self.processed):
            return "No materials have been read yet"

        status = {
            status_.material_id: status_
            for status_ in db.get_status()
        }

        spec_avg = self.log.average_of_every_materials
        res, is_first = '', True

        for material in materials:
            if not is_first:
                res = f"{res}\n\n"
            is_first = False

            material_id = material.material_id

            start = status[material_id].begin
            stop = status[material_id].end
            days = (stop - start).days + 1

            res += f"id={material_id} «{material.title}», " \
                   f"pages: {material.pages}\n" \
                   f"From {fmt(start)} to {fmt(stop)} in " \
                   f"{days} days\n" \
                   f"Average = {spec_avg.get(material_id, -1)} pages per day"
        return res

    def _reading(self) -> str:
        """
        The func if expected to make strings like that:

        id=2, «Мой лучший друг – желудок»
        will be read from 03-04-2021 to 20-04-2021 in 17 days
        254 pages read, 217 remains, 25 pages per day average

        They should be divided by double \n symbol.
        """
        if not (data := self.reading):
            return "No materials reading"

        # calculate these values one time, not every iteration
        spec_avg = self.log.average_of_every_materials
        average = self.log.average

        res, is_first = '', True

        for material, status_ in data:
            if not is_first:
                res = f"{res}\n\n"
            is_first = False

            avg = spec_avg.get(material.material_id) or average

            total_read = self.log.m_total(material.material_id)
            remains_pages = material.pages - total_read

            expected_duration = remains_pages // avg
            expected_end = today() + timedelta(days=expected_duration)

            start, stop = fmt(status_.begin), fmt(expected_end)

            res += f"id={material.material_id}, «{material.title}»\n"
            res += f"Will be read from {start} to {stop} " \
                   f"in {(expected_end - status_.begin).days} days\n" \
                   f"{total_read} pages read, " \
                   f"{remains_pages} remains, " \
                   f"average = {avg} pages per day"
        return res

    def _notes(self) -> str:
        if not (notes := self.notes):
            return "No notes found"

        key = lambda note: note.material_id
        notes = sorted(notes, key=key)

        res, is_first = '', True
        for material_id, group in groupby(notes, key=key):
            if not is_first:
                res += '\n\n'
            is_first = False

            res += f"id={material_id}, «{db.get_title(material_id)}»:\n"
            res += '\n\n'.join(
                f"\t{num}. {note.content}\n"
                f"\tAdded at: {fmt(note.date)}\n"
                f"\tChapter {note.chapter}, page {note.page}"
                for num, note in enumerate(group, 1)
            )

        return res

    @staticmethod
    def start_material(material_id: int,
                       start_date: datetime.date = None) -> None:
        """ Create item in Status table.

        :param material_id: material to start.
        :param start_date: date when the material was started.
         Today by default.

        :exception WrongDate: if start date is better than today.
        :exception MaterialNotFound: if the material doesn't exist.
        """
        try:
            db.start_material(
                material_id=material_id, start_date=start_date)
        except WrongDate as e:
            logger.error(e)
            raise
        except MaterialNotFound as e:
            logger.error(e)
            raise
        else:
            logger.info(f"Material {material_id=} started at {start_date}")

    def complete_material(self,
                          material_id: int = None,
                          completion_date: datetime.date = None) -> None:
        """
        Complete a material, set 'end' in its status.

        :param material_id: id of completed material,
         the material reading now by default.
        :param completion_date: date when the material was completed.
         Today by default.

        :exception MaterialEvenCompleted: if the material has been
         completed yet.
        :exception WrongDate: if completion_date is less than start_date.
        :exception MaterialNotAssigned: if the material has not been
         started yet.
        """
        material_id = material_id or self.log.reading_material

        try:
            db.complete_material(
                material_id=material_id,
                completion_date=completion_date
            )
        except MaterialEvenCompleted as e:
            logger.warning(e)
            raise
        except WrongDate as e:
            logger.warning(e)
            raise
        except MaterialNotAssigned as e:
            logger.warning(e)
            raise
        else:
            logger.info(f"Material {material_id=} completed "
                        f"at {completion_date=}")

    @staticmethod
    def add_material(title: str,
                     authors: str,
                     pages: int,
                     tags: str) -> None:
        db.add_material(
            title=title,
            authors=authors,
            pages=pages,
            tags=tags
        )
        logger.info("Material added")

    @staticmethod
    def get_material(material_id: int) -> db.Material:
        try:
            return db.get_materials(materials_ids=[material_id])[0]
        except IndexError:
            msg = f"Material {material_id=} not found"
            logger.warning(msg)
            raise MaterialNotFound(msg)

    @staticmethod
    def get_status(material_id: int) -> db.Status:
        return db.get_material_status(material_id=material_id)

    @staticmethod
    def get_notes(material_id: int = None) -> list[db.Note]:
        """
        :param material_id: get notes for this material.
         By default, get all notes.

        :exception ValueError: if the material_id is not integer.
        """
        if material_id is not None:
            try:
                material_id = int(material_id)
            except ValueError:
                logger.warning("Material id must be ans integer, but "
                               f"{material_id} found")
                raise
            else:
                return db.get_notes(materials_ids=[material_id])
        return db.get_notes()

    @staticmethod
    def add_note(material_id: int,
                 content: str,
                 chapter: int,
                 page: int,
                 date: datetime.date = None) -> None:
        """
        Here it is expected that all fields are valid.

        :exception MaterialNotFound: if the material doesn't exist.
        :exception ValueError: if the given page number is better
         than page count in the material.
        """
        material = Tracker.get_material(material_id)

        if material.pages < page:
            msg = f"Given page number is better than overall pages count " \
                  f"in the material, {page=} > {material.pages=}"
            logger.warning(msg)
            raise ValueError(msg)

        db.add_note(
            material_id=material_id,
            content=content,
            chapter=chapter,
            page=page,
            date=date
        )
        logger.info(f"Note for {material_id=} added")

    def __str__(self) -> str:
        """
        :return: log, materials queue and total count of read pages.
        """
        sep = '\n' + '_' * 70 + '\n'
        return f"Reading log:\n{self.log}{sep}" \
               f"Statistics:\n{self.log.statistics()}{sep}" \
               f"Materials queue:\n{self._queue()}{sep}" \
               f"Reading materials:\n{self._reading()}{sep}" \
               f"Processed materials:\n{self._processed()}"
