#!/usr/bin/env python3
import copy
import datetime
from datetime import timedelta
import logging
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
    return today() - timedelta(days=1)


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
            return list(self.keys())[-1]

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
        if date <= self.stop:
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
            return 1

    @property
    def average_of_every_materials(self) -> dict[int, int]:
        """
        Calculate average count of time spent to every material.

        The data is expected to make chart.
        """
        data = {}
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
                data[material_id] = 1

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
        step = timedelta(days=1)
        iter_ = self.start
        last_material_id = -1

        while iter_ <= self.stop:
            info = self.log.get(iter_)
            info = info or {'material_id': last_material_id, 'count': 0}

            if (material_id := info['material_id']) != last_material_id:
                last_material_id = material_id

            yield iter_, info
            iter_ += step

    def total_read(self,
                   material_id: int) -> int:
        """ Calculate how many pages of the material even read """
        return sum(
            info['count']
            for info in self.values()
            if info['material_id'] == material_id
        )

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
            avg_of_every_materials += f"\t«{title}»: {avg} pages per day"

        min_date, min_info = self.min
        max_date, max_info = self.max

        min_count, min_id = min_info['count'], min_info['material_id']
        max_count, max_id = max_info['count'], max_info['material_id']

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
            if (material_id := info['material_id']) != last_material_id:
                last_material_id = material_id
                last_material_title = f"«{db.get_title(material_id)}»"
            else:
                last_material_title = '...'

            item = f"{new_line * (not is_first)}{fmt(date)}: " \
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
    def processed(self) -> list[db.Material]:
        """ Get list of completed Materials. """
        return db.get_completed_materials()

    @property
    def reading(self) -> list[tuple[db.Material, db.Status]]:
        """ Get reading materials and their statuses """
        return db.get_reading_materials()

    @property
    def log(self) -> Log:
        return self.__log

    @property
    def notes(self) -> list[db.Note]:
        return db.get_notes()

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
                   f"{days} {INFLECT_DAY(days)}\n" \
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

            total_read = self.log.total_read(material.material_id)
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

            res += f"id={material_id}, «{db.get_title(material_id)}»: "
            res += '\n'.join(
                f"\t{num}. {note.content}\n"
                f"Added at {fmt(note.date)}\n"
                f"\tChapter {note.chapter}, page {note.page}"
                for num, note in enumerate(group, 1)
            )

        return res

    @staticmethod
    def start_material(*,
                       material_id: int,
                       start_date: datetime.date = None) -> None:
        try:
            db.start_material(
                material_id=material_id, start_date=start_date)
        except db.WrongDate:
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
                completion_date=completion_date
            )
        except db.MaterialEvenCompleted as e:
            logging.error(e)
            raise
        except db.WrongDate as e:
            logging.error(e)
            raise
        except db.MaterialNotAssigned as e:
            logging.error(e)
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

    @staticmethod
    def get_status(material_id: int) -> db.Material:
        return db.get_material_status(material_id=material_id)

    @staticmethod
    def get_notes(material_id: int) -> list[db.Note]:
        return db.get_notes(materials_ids=[material_id])

    @staticmethod
    def add_note(material_id: int,
                 content: str,
                 chapter: int,
                 page: int,
                 date: datetime.date = None) -> None:
        try:
            material = db.get_materials(materials_ids=[material_id])[0]
        except IndexError:
            msg = f"Material {material_id} not found"
            logging.error(msg)
            raise db.MaterialNotFound(msg)

        if material.pages < page:
            raise ValueError("Given page more than overall "
                             "pages count in the material,"
                             f"{page} > {material.pages}")

        db.add_note(
            material_id=material_id,
            content=content,
            chapter=chapter,
            page=page,
            date=date
        )

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
