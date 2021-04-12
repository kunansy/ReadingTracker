#!/usr/bin/env python3
import copy
import datetime
import logging
from collections import defaultdict
from itertools import groupby
from pathlib import Path
from typing import Union, Optional, Iterator

import ujson

import src.db_api as db


DATA_FOLDER = Path('data')
LOG_TYPE = dict[datetime.date, dict[str, int]]
PAGES_PER_DAY = 50
INDENT = 2

DATE_FORMAT = '%d-%m-%Y'
DATE_TYPE = Union[str, datetime.date, datetime.datetime]


def with_num(word: str,
             num: int) -> str:
    """
    Make the word agree with the number.
    Means add -s if num > 1.

    :param word: English word to make agree with the number.
    :param num: num.
    :return: word with -s or without.
    """
    return f"{word}{'s' * (num > 1)}"


def inflect_word(word: str):
    def wrapped(num: int) -> str:
        return with_num(word, num)

    return wrapped


INFLECT_PAGE = inflect_word('page')
INFLECT_DAY = inflect_word('day')


def today() -> datetime.date:
    return datetime.date.today()


def yesterday() -> datetime.date:
    return today() - datetime.timedelta(days=1)


def to_datetime(date: DATE_TYPE) -> Optional[datetime.date]:
    if date is None:
        return

    if isinstance(date, str):
        try:
            date = datetime.datetime.strptime(date, DATE_FORMAT)
            date = date.date()
        except ValueError as e:
            raise ValueError(f"Wrong str format\n{e}")
        else:
            return date
    elif isinstance(date, datetime.datetime):
        return date.date()
    elif isinstance(date, datetime.date):
        return date
    else:
        raise TypeError(f"Str or datetime expected, {type(date)} found")


def fmt(date: datetime.date) -> str:
    return date.strftime(DATE_FORMAT)


class Log:
    __slots__ = '__log'

    LOG_PATH = DATA_FOLDER / 'log.json'

    def __init__(self) -> None:
        try:
            self.__log = self._get_log()
        except Exception as e:
            logging.error(f"When load the log: {e}")
            raise

    @property
    def log(self) -> LOG_TYPE:
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
            return today()

    @property
    def reading_material(self) -> int:
        """ Get id of the reading material. """
        try:
            return list(self.log.values())[-1]['material_id']
        except IndexError:
            logging.exception("Reading log is empty, no materials found")
            raise

    def _get_log(self) -> LOG_TYPE:
        """
        Get log from JSON file and parse it.
        Convert keys to datetime.date, values to int.

        :return: dict with the format.
        :exception ValueError: if the file if empty.
        """
        with self.path.open(encoding='utf-8') as f:
            log = ujson.load(f)

            return {
                to_datetime(date): info
                for date, info in log.items()
            }

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
        if date > self.stop:
            raise ValueError("The date must be less than today,"
                             f"but {date=} > {self.stop=}")
        if (date := to_datetime(date)) in self.__log:
            raise ValueError(f"The {date=} even exists in the log")
        if material_id is None and len(self.log) == 0:
            raise ValueError(f"{material_id=} and log dict is empty")

        self.__log[date] = {
            'material_id': material_id or self.reading_material,
            'count': count
        }
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
            logging.exception(f"Cannot set today's log with "
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
            logging.exception(f"Cannot set yesterday's log with "
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
            info['count']
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
            return 0

    @property
    def average_of_every_materials(self) -> dict[int, int]:
        """
        Calculate average count of time spent to every material.

        The data is expected to make chart.
        """
        data = defaultdict(int)

        key_ = lambda item: item[1]['material_id']
        sample = sorted(self.data(), key=key_)

        status = {
            status_.material_id: status_
            for status_ in db.get_status()
        }

        for material_id, group in groupby(sample, key=key_):
            days = count = 0
            for date, info in group:
                if (item := status.get(info['material_id'])) and item.end and \
                        date > item.end:
                    break
                days += 1
                count += info['count']

            try:
                data[material_id] = count // days
            except ZeroDivisionError:
                data[material_id] = 0

        return dict(sorted(
            data.items(), key=lambda item: item[1], reverse=True))

    @property
    def min(self) -> tuple[datetime.date, dict[str, int]]:
        return min(
            [(date, info) for date, info in self.items()],
            key=lambda item: item[1]['count']
        )

    @property
    def max(self) -> tuple[datetime.date, dict[str, int]]:
        return max(
            [(date, info) for date, info in self.items()],
            key=lambda item: item[1]['count']
        )

    @property
    def median(self) -> int:
        counts = sorted(
            info['count']
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

    def data(self) -> Iterator[tuple[datetime.date, dict[str, int]]]:
        """ Get pairs: date, info of all days from start to stop.
        The function is expected to make graphics.

        If the day is empty, material_id is supposed
        as the material_id of the last not empty day.
        """
        step = datetime.timedelta(days=1)
        iter_ = self.start
        last_material_id = -1

        while iter_ <= self.stop:
            info = self.log.get(iter_)
            info = info or {'material_id': last_material_id, 'count': 0}

            if (material_id := info['material_id']) != last_material_id:
                last_material_id = material_id

            yield iter_, info
            iter_ += step

    def dates(self) -> list[datetime.date]:
        return [
            date
            for date, _ in self.data()
        ]

    def counts(self) -> list[int]:
        return [
            info['count']
            for _, info in self.data()
        ]

    def copy(self):
        new_log = self
        new_log.__log = copy.deepcopy(self.log)

        return new_log

    def statistics(self) -> str:
        avg_of_every_materials, is_first = '', True

        for material_id, avg in self.average_of_every_materials.items():
            if not is_first:
                avg_of_every_materials += '\n'
            is_first = False

            title = db.get_title(material_id)
            avg_of_every_materials += f"\t«{title}»: {avg}"

        min_date, min_info = self.min
        max_date, max_info = self.max

        min_count = min_info['count']
        max_count = max_info['count']

        min_id = min_info['material_id']
        max_id = max_info['material_id']

        min_title = db.get_title(min_id)
        max_title = db.get_title(max_id)

        min_date, max_date = fmt(min_date), fmt(max_date)

        return f"Duration: {self.duration} days\n" \
               f"Empty days: {self.empty_days}\n" \
               f"Max: {max_date} = {max_count}, «{max_title}»\n" \
               f"Min: {min_date} = {min_count}, «{min_title}»\n" \
               f"Average: {self.average} pages per day\n" \
               f"Median: {self.median} pages\n" \
               f"Total pages count: {self.total}\n" \
               f"Would be total: {self.would_be_total}\n" \
               f"Average of every material: \n{avg_of_every_materials}"

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

        if step is None:
            step = datetime.timedelta(days=1)
        else:
            step = datetime.timedelta(days=step)

        iter_ = start
        new_log_content = {}
        new_log = self.copy()

        while iter_ < stop:
            if start <= iter_ <= stop:
                if iter_ in new_log.log:
                    new_log_content[iter_] = new_log.log[iter_]
            else:
                break
            iter_ += step
        new_log.__log = new_log_content
        return new_log

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
            if (material_id := info['material_id']) != last_material_id:
                last_material_id = material_id
                last_material_title = f"«{db.get_title(material_id)}»"
            else:
                last_material_title = '...'

            date = date.strftime(DATE_FORMAT)
            item = f"{new_line * (not is_first)}{date}: " \
                   f"{info['count']}, {last_material_title}"

            is_first = False
            res = f"{res}{item}"

        return res

    def __repr__(self) -> str:
        if len(self.log) == 0:
            return f"{self.__class__.__name__}()"

        res = f'{self.__class__.__name__}(\n'
        res += '\n'.join(
            f"\t{key=}: {val=}"
            for key, val in self.log.items()
        )
        return res + '\n)'


class Tracker:
    __slots__ = (
        '__materials', '__log'
    )

    BOOKS_PATH = DATA_FOLDER / 'materials.json'

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
    def processed(self) -> list[db.Material]:
        """ Get list of completed Materials. """
        return db.get_completed_materials()

    @property
    def log(self) -> Log:
        return self.__log

    def _str_queue(self) -> str:
        """
        :return: converted to str queue.
        """
        if len(self.queue) == 0:
            return "No materials in queue"

        res = ''

        last_date = self.start_date
        for material in self.queue:
            days_count = material.pages // (self.log.avg + 1)
            finish_date = last_date + datetime.timedelta(days=days_count)

            days = f"{days_count} {INFLECT_DAY(days_count)}"
            res += f"«{material.title}» will be read\n"

            start = last_date.strftime(DATE_FORMAT)
            stop = finish_date.strftime(DATE_FORMAT)
            res += f"from {start} to {stop} in {days}\n\n"

            last_date = finish_date + datetime.timedelta(days=1)
        return f"{res.strip()}\n{'-' * 70}"

    def _str_processed(self) -> str:
        """
        :return: converted to str processed list.
        """
        if len(self.processed) == 0:
            return "No materials have been read yet"

        res = ''
        for material in self.processed:
            res += f"«{material.title}», pages: {material.pages} has been read\n"

            start = material.start_date.strftime(DATE_FORMAT)
            stop = material.end_date.strftime(DATE_FORMAT)
            days = (material.end_date - material.start_date).days

            res += f"From {start} by {stop} in {days} {INFLECT_DAY(days)}\n"
        return res

    @staticmethod
    def start_material(*,
                       material_id: int,
                       start_date: datetime.date = None) -> None:
        try:
            db.start_material(
                material_id=material_id, start_date=start_date)
        except ValueError:
            logging.exception(f"date format is wrong, {start_date=}")

    def complete_material(self,
                          *,
                          material_id: int = None,
                          completion_date: datetime.date = None) -> None:
        """
        Complete a material, set 'end' in its status.

        :param material_id: id of completed material,
         the material reading now by default.
        :param completion_date: date when the material was completed.
         Today by default.

        :exception ValueError: if the material has been completed
         yet or if 'completion_date' is less than start date.

        :exception IndexError: if the material has not been started yet.
        """
        material_id = material_id or self.log.reading_material

        try:
            db.complete_material(
                material_id=material_id,
                completion_date=completion_date)
        except ValueError:
            logging.exception(
                f"Cannot complete {material_id=}, {completion_date=}")
            raise
        except IndexError:
            logging.exception(f"{material_id=} has ot been started yet")
            raise

    @staticmethod
    def append(title: str,
               authors: str,
               pages: str,
               tags: str) -> None:
        """
        Add a material.

        :param title: material's title.
        :param authors: material's authors.
        :param pages: count of pages.
        :param tags: tags
        """
        material = {
            'title': title,
            'authors': authors,
            'pages': pages,
            'tags': tags
        }
        db.add_materials([material])

    def __str__(self) -> str:
        """
        :return: log, materials queue and total count of read pages.
        """
        return f"Reading log:\n{self.log}\n" \
               f"Materials queue:\n{self._str_queue()}\n" \
               f"Processed materials:\n{self._str_processed()}"

