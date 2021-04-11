#!/usr/bin/env python3
import datetime
from pathlib import Path
from typing import Iterator, Union, Optional

import ujson

import src.models as db


DATA_FOLDER = Path('data')
LOG_TYPE = dict[datetime.date, int]
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


class Log:
    __slots__ = '__log'

    LOG_PATH = DATA_FOLDER / 'log.json'

    def __init__(self) -> None:
        try:
            log = self._get_log()
        except Exception:
            log = {}
        self.__log = log

    @property
    def log(self) -> LOG_TYPE:
        return self.__log

    @property
    def path(self) -> Path:
        return self.LOG_PATH

    @property
    def start(self) -> Optional[datetime.date]:
        try:
            return list(self.log.keys())[0]
        except IndexError:
            pass

    def _get_log(self) -> dict[datetime.date, dict[str, int]]:
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
        :param count: count of read pages, listened lectures etc.
        :param material_id: id of the learned material,
        by default id of the last material if exists.

        :exception ValueError: if count <= 0, the date
        is more than today, the date even exists in
        log, 'material_id' is None and log is empty.
        """
        if count <= 0:
            raise ValueError(f"Count must be > 0, but 0 <= {count}")
        if date > today():
            raise ValueError("The date must be less than today,"
                             f"but {date=} > {today()=}")
        if (date := to_datetime(date)) in self.__log:
            raise ValueError(f"The {date=} even exists in the log")
        if material_id is None and len(self.log) == 0:
            raise ValueError(f"{material_id=} and log dict is empty")

        material_id = material_id or list(self.log.values())[-1]['material_id']

        self.__log[date] = {
            'material_id': material_id,
            'count': count
        }
        self.__log = dict(sorted(self.log.items(), key=lambda i: i[0]))

    def set_today_log(self,
                      count: int,
                      material_id: int = None) -> None:
        """
        Set today's reading log.

        :param count: count of materials learned today.
        :param material_id: id of learned material.
        The last learned material_id by default.
        """
        self._set_log(today(), count, material_id)

    def set_yesterday_log(self,
                          count: int,
                          material_id: int = None) -> None:
        """
        Set yesterday's reading log.

        :param count: count of materials learned yesterday.
        :param material_id: id of learned material.
        The last learned material_id by default.
        """
        self._set_log(yesterday(), count, material_id)

    def dump(self) -> None:
        """ Dump dict to the log file. """

        data_str = {
            date.strftime(DATE_FORMAT): count
            for date, count in self.log.items()
        }

        with self.path.open('w', encoding='utf-8') as f:
            ujson.dump(data_str, f, indent=INDENT)

    def __str__(self) -> str:
        """
        If there are the same material on several days,
        add title of it in the first day and '...' to next
        one instead of printing out the title every time.
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
        self.__materials = self._get_materials()
        self.__log = log

    @property
    def log(self) -> Log:
        """
        :return: reading Log.
        """
        return self.__log

    @property
    def materials(self) -> dict:
        """
        :return: materials.
        """
        return self.__materials

    @property
    def queue(self) -> list[Material]:
        """
        :return: list of Materials in queue.
        """
        return self.materials.get('queue', [])

    @property
    def processed(self) -> list[Material]:
        """
        :return: list of Materials in processed.
        """
        return self.materials.get('processed', [])

    @property
    def start_date(self) -> datetime.date:
        """
        :return: date when reading of the first material started.
        """
        return self[1].start_date

    def _get_materials(self) -> dict[str, list[Material]]:
        """
        :return: materials.
        """
        with self.BOOKS_PATH.open(encoding='utf-8') as f:
            materials = ujson.load(f)

        return {
            'queue': [
                Material(**material)
                for material in materials['queue']
            ],
            'processed': [
                Material(**material)
                for material in materials['processed']
            ]
        }

    def dump(self) -> None:
        """ Dump materials. """
        res = {
            'queue': [
                material.json()
                for material in self.queue
            ],
            'processed': [
                material.json()
                for material in self.processed
            ]
        }

        with self.BOOKS_PATH.open('w', encoding='utf-8') as f:
            ujson.dump(res, f, indent=INDENT, ensure_ascii=False)

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

    def print_queue(self) -> None:
        """ Print materials queue. """
        print(self._str_queue())

    def print_processed(self) -> None:
        """ Print processed materials. """
        print(self._str_processed())

    def complete_material(self,
                          completed_date: datetime.date = None) -> None:
        """
        Move the first material in 'queue' to 'processed'.

        :param completed_date: date when the material was completed.
        Today by default.

        :exception ValueError: if the materials queue is empty.
        """
        if len(self.queue) == 0:
            raise ValueError("Materials queue is empty")

        material = self.queue.pop(0)

        completed_date = completed_date or today()
        material.end_date = completed_date
        self.processed.append(material)

        self.queue[0].start_date = completed_date + datetime.timedelta(days=1)

    def _last_id(self) -> int:
        """
        :return: id of the last material in queue.
         0 if the query is empty.
        """
        if len(self.queue) == 0:
            return 0
        return self.queue[-1].id

    def push_back(self,
                  title: str,
                  authors: str,
                  pages: int) -> None:
        """
        Add a material to the end of the queue.

        Id will be calculated as id
        of the last material + 1.

        :param title: material's title.
        :param authors: material's authors.
        :param pages: count of pages in the material.
        """
        material = Material(
            self._last_id() + 1, title, authors, pages
        )
        self.queue.append(material)

    def push_front(self,
                   title: str,
                   authors: str,
                   pages: int) -> None:
        """
        Add a material to the begin of the queue.

        Id will be calculated as id
         of the last material + 1.

        :param title: material's title.
        :param authors: material's authors.
        :param pages: count of pages in the material.
        """
        material = Material(
            self._last_id() + 1, title, authors, pages
        )
        self.queue.insert(0, material)

    def __in(self,
             **kwargs) -> Iterator[Material]:
        where = kwargs.pop('where', 'queue')
        for material in getattr(self, where):
            if all(
                getattr(material, arg) == val
                for arg, val in kwargs.items()
            ):
                yield material

    def in_queue(self,
                 **kwargs) -> list[Material]:
        """
        :param kwargs: pairs: atr name - atr value.
        :return: list of Materials with these params from queue.
        """
        try:
            res = [
                material
                for material in self.__in(where='queue', **kwargs)
            ]
        except AttributeError:
            raise AttributeError("Material obj has no given attribute")
        else:
            return res

    def in_processed(self,
                     **kwargs) -> list[Material]:
        """
        :param kwargs: pairs: atr name - atr value.
        :return: list of Materials with these params from processed.
        """
        try:
            res = [
                material
                for material in self.__in(where='processed', **kwargs)
            ]
        except AttributeError:
            raise AttributeError("Material obj has no given attribute")
        else:
            return res

    def __str__(self) -> str:
        """
        :return: log, materials queue and total count of read pages.
        """
        return f"Reading log:\n{self.log}\n" \
               f"Materials queue:\n{self._str_queue()}\n" \
               f"Processed materials:\n{self._str_processed()}"

    def __contains__(self,
                     id_: int) -> bool:
        """
        :param id_: material's id.
        :return: whether the queue contains the material at id.
        """
        return bool(self.in_queue(id=id_) + self.in_processed(id=id_))

    def __getitem__(self,
                    id_: int) -> Material:
        if id_ not in self:
            raise IndexError(f"Material with `{id_=}` doesn't exist")

        for material in self.queue + self.processed:
            if material.id == id_:
                return material
