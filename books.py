#!/usr/bin/env python3
import argparse
import datetime
from pathlib import Path
from typing import Dict, List, Iterator, Union

import ujson

DATA_FOLDER = Path('data')
LOG_TYPE = Dict[datetime.date, int]
PAGES_PER_DAY = 50
INDENT = 2

DATE_FORMAT = '%d.%m.%Y'
DATE_TYPE = Union[str, datetime.date, datetime.datetime]


def with_num(word: str, num: int) -> str:
    """
    Make the word agree with the number.
    Means add -s if num > 1.

    :param word: str, English word to make agree with the number.
    :param num: int, num.
    :return: str, word with -s or without.
    """
    return f"{word}{'s' * (num > 1)}"


def inflect_word(word: str):
    def wrapped(num: int) -> str:
        return with_num(word, num)

    return wrapped


INFLECT_PAGE = inflect_word('page')
INFLECT_DAY = inflect_word('day')


def today() -> datetime.date:
    """
    :return: datetime.date, today.
    """
    return datetime.date.today()


def yesterday() -> datetime.date:
    """
    :return: datetime.date, yesterday.
    """
    return today() - datetime.timedelta(days=1)


def to_datetime(date: DATE_TYPE) -> datetime.date:
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
        """
        :return: dict, reading log.
        """
        return self.__log

    @property
    def path(self) -> Path:
        """
        :return: Path to log file.
        """
        return self.LOG_PATH

    @property
    def avg(self) -> int:
        """
        :return: int, average count of read pages.
        """
        try:
            return sum(self.log.values()) // len(self.log)
        except ZeroDivisionError:
            return 0

    @property
    def total(self) -> int:
        """
        :return: int, total count of read pages.
        """
        return sum(self.log.values())

    def _get_log(self) -> Dict[datetime.date, int]:
        """
        Get log from the file and parse it to JSON dict.
        Convert keys to datetime.date, values to int.

        :return: JSON dict with the format.
        :exception ValueError: if the file if empty.
        """
        with self.path.open(encoding='utf-8') as f:
            log = ujson.load(f)

            res = {}
            for date, count in log.items():
                res[to_datetime(date)] = count
        return res

    def _set_log(self,
                 date: datetime.date,
                 pages: int) -> None:
        """
        Set reading log for the day.
        Check arguments valid.
        Sort the log by dates.

        :param date: datetime.date or str, date of read.
        :param pages: int, count of read pages.
        :return: None.

        :exception ValueError: of pages < 0 or date format is wrong.
        """
        if pages < 0:
            raise ValueError("Pages count must be >= 0")

        date = to_datetime(date)
        if date in self.__log:
            raise ValueError(f"The date {date} even exists in the log")

        self.__log[date] = pages
        self.__log = dict(sorted(self.log.items(), key=lambda i: i[0]))

    def set_today_log(self,
                      pages: int) -> None:
        """
        Set today's reading log.

        :param pages: int, count of pages read today.
        :return: None.
        """
        self._set_log(today(), pages)

    def set_yesterday_log(self,
                          pages: int) -> None:
        """
        Set yesterday's reading log.

        :param pages: int, count of pages read yesterday.
        :return: None.
        """
        self._set_log(yesterday(), pages)

    def _str_log(self) -> str:
        """
        Convert log to str to print.

        :return: this str.
        """
        if len(self.log) == 0:
            return "Reading log is empty"

        res = ''
        sum_ = 0

        for date, read_pages in self.log.items():
            date = date.strftime(DATE_FORMAT)
            res += f"{date}: {read_pages} " \
                   f"{INFLECT_PAGE(read_pages)}\n"
            sum_ += read_pages
        res += '\n'

        avg = self.avg
        res += f"Average {avg} {INFLECT_PAGE(avg)}\n"

        res += "And that is "
        diff = abs(PAGES_PER_DAY - avg)
        if avg == PAGES_PER_DAY:
            res += "equal to expected count"
        elif avg < PAGES_PER_DAY:
            res += f"{diff} less than expected"
        else:
            res += f"{diff} better than expected"

        return f"{res}\n{'-' * 70}"

    def _str_total(self) -> str:
        """
        Get total count of read pages to print.

        :return: this str.
        """
        if len(self.log) == 0:
            return "Reading log is empty"

        return f"Total pages read: {self.total}\n" \
               f"{'-' * 70}"

    def print_log(self) -> None:
        """
        Print reading log.

        :return: None.
        """
        print(self._str_log())

    def print_total(self) -> None:
        """
        Print total count of read pages.

        :return: None.
        """
        print(self._str_total())

    def dump(self) -> None:
        """
        Dump dict to the log file.

        :return: None.
        """
        data_str = {}
        for date, count in self.log.items():
            data_str[date.strftime(DATE_FORMAT)] = count

        with self.path.open('w', encoding='utf-8') as f:
            ujson.dump(data_str, f, indent=INDENT)

    def __str__(self) -> str:
        if len(self.log) == 0:
            return "Reading log is empty"

        return f"{self._str_log()}\n" \
               f"{self._str_total()}"

    def __repr__(self) -> str:
        if len(self.log) == 0:
            return f"{self.__class__.__name__}()"

        res = f'{self.__class__.__name__}(\n'
        res += '\n'.join(
            f"\t{key=}: {val=}"
            for key, val in self.log.items()
        )
        return res + '\n)'


class Material:
    __slots__ = (
        '__id', '__title', '__author',
        '__pages', '__start_date', '__end_date'
    )

    def __init__(self,
                 id: int,
                 title: str,
                 author: str,
                 pages: int,
                 start_date: datetime.date = None,
                 end_date: datetime.date = None) -> None:
        self.__id = id
        self.__title = title
        self.__author = author
        self.__pages = pages
        self.__start_date = None
        self.__end_date = None

        self.start_date = start_date
        self.end_date = end_date

    @property
    def id(self) -> int:
        """
        :return: int, material's id.
        """
        return self.__id

    @property
    def title(self) -> str:
        """
        :return: str, material's title.
        """
        return self.__title

    @property
    def author(self) -> str:
        """
        :return: str, material's authors.
        """
        return self.__author

    @property
    def pages(self) -> int:
        """
        :return: int, count of material's pages.
        """
        return self.__pages

    @property
    def start_date(self) -> datetime.date:
        """
        :return: datetime.date, date when the material was started.
        """
        return self.__start_date

    @property
    def end_date(self) -> datetime.date:
        """
        :return: datetime.date, date when the material was finished.
        """
        return self.__end_date

    @start_date.setter
    def start_date(self,
                   date: datetime.date or str) -> None:
        """
        :param date: datetime.date or str, new start_date value.
        :return: None.

        :exception ValueError: if the date is str with wrong format.
        """
        self.__start_date = to_datetime(date)

    @end_date.setter
    def end_date(self,
                 date: datetime.date or str) -> None:
        """
        :param date: datetime.date or str, new end_date value.
        :return: None.

        :exception ValueError: if the date is str with wrong format.
        """
        self.__end_date = to_datetime(date)

    def json(self) -> dict:
        """
        :return: dict, fields' names and their values.
        """
        json = {
            'id': self.id,
            'title': self.title,
            'author': self.author,
            'pages': self.pages
        }
        if self.start_date is not None:
            json['start_date'] = self.start_date.strftime(DATE_FORMAT)

        if self.end_date is not None:
            json['end_date'] = self.end_date.strftime(DATE_FORMAT)

        return json

    def __str__(self) -> str:
        return '\n'.join(
            f"{key}: {val}"
            for key, val in self.json().items()
        )

    def __repr__(self) -> str:
        res = f'{self.__class__.__name__}(\n'
        res += '\n'.join(
            f"\t{key=}: {val=}"
            for key, val in self.json().items()
        )
        return res + '\n)'


class MaterialsQueue:
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
        :return: dict, materials.
        """
        return self.__materials

    @property
    def queue(self) -> List[Material]:
        """
        :return: list of Materials in queue.
        """
        return self.materials.get('queue', [])

    @property
    def processed(self) -> List[Material]:
        """
        :return: list of Materials in processed.
        """
        return self.materials.get('processed', [])

    @property
    def start_date(self) -> datetime.date:
        """
        :return: datetime.date, date when reading
         of the first material started.
        """
        return self[1].start_date

    def _get_materials(self) -> Dict[str, List[Material]]:
        """
        :return: dict, materials.
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
        """
        Dump materials.

        :return: None.
        """
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
        Convert materials queue to str to print.

        :return: this str.
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
        Convert processed to str to print.

        :return: this str.
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
        """
        Print materials queue.

        :return: None.
        """
        print(self._str_queue())

    def print_processed(self) -> None:
        """
        Print processed materials.

        :return: None.
        """
        print(self._str_processed())

    def complete_material(self,
                          completed_date: datetime.date = None) -> None:
        """
        Move the first material in 'queue' to 'processed'.

        :param completed_date: datetime.date or str with DATE_FORMAT,
         date when the material was completed. Today by default.
        :return: None.

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
        :return: int, id of the last material in queue.
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

        :param title: str, material's title.
        :param authors: str, material's authors.
        :param pages: int, count of pages in the material.

        :return: None.
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

        :param title: str, material's title.
        :param authors: str, material's authors.
        :param pages: int, count of pages in the material.

        :return: None.
        """
        material = Material(
            self._last_id() + 1, title, authors, pages
        )
        self.queue.insert(material, 0)

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
                 **kwargs) -> List[Material]:
        """
        :param kwargs: pairs: atr name - atr value.
        :return: list of Materials with these params from queue.
        """
        try:
            res = [
                material
                for material in self.__in(where='queue', **kwargs)
            ]
        except AttributeError as e:
            raise AttributeError(f"Material obj has no given attribute\n{e}")
        else:
            return res

    def in_processed(self,
                     **kwargs) -> List[Material]:
        """
        :param kwargs: pairs: atr name - atr value.
        :return: list of Materials with there params from processed.
        """
        try:
            res = [
                material
                for material in self.__in(where='processed', **kwargs)
            ]
        except AttributeError as e:
            raise AttributeError(f"Material obj has no given attribute\n{e}")
        else:
            return res

    def __str__(self) -> str:
        """
        Get log, materials queue and total cunt of read pages.

        :return: this str.
        """
        return f"Reading log:\n{self.log}\n" \
               f"Materials queue:\n{self._str_queue()}\n" \
               f"Processed materials:\n{self._str_processed()}"

    def __contains__(self,
                     id_: int) -> bool:
        """
        Whether the queue contains the material at id.

        :param id_: int, material's id.
        :return: bool.
        """
        return bool(self.in_queue(id=id_) + self.in_processed(id=id_))

    def __getitem__(self,
                    id_: int) -> Material:
        if id_ not in self:
            raise IndexError(f"Material with `{id_=}` doesn't exist")

        for material in self.queue + self.processed:
            if material.id == id_:
                return material


def is_ok(num: int or None) -> bool:
    """
    Check that the arg is int > 0.

    :param num: int or None, value to validate.
    :return: bool, whether the arg is int > 0.
    """
    return num is not None and num >= 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Materials to read, processed materials and reading log"
    )
    parser.add_argument(
        '-pl', '--print-log',
        help="Print reading log",
        default=False,
        action="store_true",
        dest='pl'
    )
    parser.add_argument(
        '-pq', '--print-queue',
        help="Print materials queue",
        default=False,
        action="store_true",
        dest='pq'
    )
    parser.add_argument(
        '-pp', '--print-processed',
        help="Print processed materials",
        default=False,
        action="store_true",
        dest='pp'
    )
    parser.add_argument(
        '-pt', '--print-total',
        help="Print total count of read pages",
        default=False,
        action="store_true",
        dest='pt'
    )
    parser.add_argument(
        '-pall', '--print-all',
        help="Print all: reading log, materials queue, " /
             "processed materials, total read pages count",
        default=False,
        action="store_true",
        dest='pall'
    )
    parser.add_argument(
        '-tday', '--today',
        help="Set count of pages read today",
        type=int,
        dest='today',
        required=False
    )
    parser.add_argument(
        '-yday', '--yesterday',
        help="Set count of pages read yesterday",
        type=int,
        dest='yesterday',
        required=False
    )
    parser.add_argument(
        '-cb', '--complete-material',
        help="Move the first material from 'queue' to 'processed'",
        default=False,
        action="store_true",
        dest='cb'
    )
    args = parser.parse_args()
    log = Log()
    materials_queue = MaterialsQueue(log)

    if is_ok(args.today):
        log.set_today_log(args.today)
        log.dump()
    if is_ok(args.yesterday):
        log.set_yesterday_log(args.yesterday)
        log.dump()

    if args.cb:
        materials_queue.complete_material()
        materials_queue.dump()

    if args.pall:
        print(materials_queue)
    else:
        if args.pl:
            log.print_log()
        if args.pt:
            log.print_total()
        if args.pq:
            materials_queue.print_queue()
        if args.pp:
            materials_queue.print_processed()


if __name__ == "__main__":
    main()

