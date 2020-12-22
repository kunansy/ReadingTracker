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


class Book:
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
        :return: int, book's id.
        """
        return self.__id

    @property
    def title(self) -> str:
        """
        :return: str, book's title.
        """
        return self.__title

    @property
    def author(self) -> str:
        """
        :return: str, book's authors.
        """
        return self.__author

    @property
    def pages(self) -> int:
        """
        :return: int, count of book's pages.
        """
        return self.__pages

    @property
    def start_date(self) -> datetime.date:
        """
        :return: datetime.date, date when the book was started.
        """
        return self.__start_date

    @property
    def end_date(self) -> datetime.date:
        """
        :return: datetime.date, date when the book was finished.
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


class BooksQueue:
    __slots__ = (
        '__books', '__log'
    )

    BOOKS_PATH = DATA_FOLDER / 'books.json'

    def __init__(self,
                 log: Log) -> None:
        self.__books = self._get_books()
        self.__log = log

    @property
    def log(self) -> Log:
        """
        :return: reading Log.
        """
        return self.__log

    @property
    def books(self) -> dict:
        """
        :return: dict, books.
        """
        return self.__books

    @property
    def queue(self) -> List[Book]:
        """
        :return: list of Books in queue.
        """
        return self.books.get('queue', [])

    @property
    def processed(self) -> List[Book]:
        """
        :return: list of Books in processed.
        """
        return self.books.get('processed', [])

    @property
    def start_date(self) -> datetime.date:
        """
        :return: datetime.date, date when reading
         of the first book started.
        """
        return self[1].start_date

    def _get_books(self) -> Dict[str, List[Book]]:
        """
        :return: dict, books.
        """
        with self.BOOKS_PATH.open(encoding='utf-8') as f:
            books = ujson.load(f)

        return {
            'queue': [
                Book(**book)
                for book in books['queue']
            ],
            'processed': [
                Book(**book)
                for book in books['processed']
            ]
        }

    def dump(self) -> None:
        """
        Dump books.

        :return: None.
        """
        res = {
            'queue': [
                book.json()
                for book in self.queue
            ],
            'processed': [
                book.json()
                for book in self.processed
            ]
        }

        with self.BOOKS_PATH.open('w', encoding='utf-8') as f:
            ujson.dump(res, f, indent=INDENT, ensure_ascii=False)

    def _str_queue(self) -> str:
        """
        Convert books queue to str to print.

        :return: this str.
        """
        if len(self.queue) == 0:
            return "No books in queue"

        res = ''

        last_date = self.start_date
        for book in self.queue:
            days_count = book.pages // (self.log.avg + 1)
            finish_date = last_date + datetime.timedelta(days=days_count)

            days = f"{days_count} {INFLECT_DAY(days_count)}"
            res += f"«{book.title}» will be read\n"

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
            return "No books have been read yet"

        res = ''
        for book in self.processed:
            res += f"«{book.title}», pages: {book.pages} has been read\n"

            start = book.start_date.strftime(DATE_FORMAT)
            stop = book.end_date.strftime(DATE_FORMAT)
            days = (book.end_date - book.start_date).days

            res += f"From {start} by {stop} in {days} {INFLECT_DAY(days)}\n"
        return res

    def print_queue(self) -> None:
        """
        Print books queue.

        :return: None.
        """
        print(self._str_queue())

    def print_processed(self) -> None:
        """
        Print processed books.

        :return: None.
        """
        print(self._str_processed())

    def complete_book(self,
                      completed_date: datetime.date = None) -> None:
        """
        Move the first book in 'queue' to 'processed'.

        :param completed_date: datetime.date or str with DATE_FORMAT,
         date when the book was completed. Today by default.
        :return: None.

        :exception ValueError: if the books queue is empty.
        """
        if len(self.queue) == 0:
            raise ValueError("Books queue is empty")

        book = self.queue.pop(0)

        completed_date = completed_date or today()
        book.end_date = completed_date
        self.processed.append(book)

        self.queue[0].start_date = completed_date + datetime.timedelta(days=1)

    def _last_id(self) -> int:
        """
        :return: int, id of the last book in queue.
         0 if the query is empty.
        """
        if len(self.queue) == 0:
            return 0
        return self.queue[-1].id

    def add_book(self,
                 title: str,
                 authors: str,
                 pages: int) -> None:
        """
        Add book to and and the queue.

        Id will be calculated as id
        of the last book + 1.

        :param title: str, book's title.
        :param authors: str, book's authors.
        :param pages: int, count of pages in the book.

        :return: None.
        """
        book = Book(
            self._last_id() + 1, title, authors, pages
        )
        self.queue.append(book)

    def __in(self,
             **kwargs) -> Iterator[Book]:
        where = kwargs.pop('where', 'queue')
        for book in getattr(self, where):
            if all(
                getattr(book, arg) == val
                for arg, val in kwargs.items()
            ):
                yield book

    def in_queue(self,
                 **kwargs) -> List[Book]:
        """
        :param kwargs: pairs: atr name - atr value.
        :return: list of Books with these params from queue.
        """
        try:
            res = [
                book
                for book in self.__in(where='queue', **kwargs)
            ]
        except AttributeError as e:
            raise AttributeError(f"Book obj has no given attribute\n{e}")
        else:
            return res

    def in_processed(self,
                     **kwargs) -> List[Book]:
        """
        :param kwargs: pairs: atr name - atr value.
        :return: list of Books with there params from processed.
        """
        try:
            res = [
                book
                for book in self.__in(where='processed', **kwargs)
            ]
        except AttributeError as e:
            raise AttributeError(f"Book obj has no given attribute\n{e}")
        else:
            return res

    def __str__(self) -> str:
        """
        Get log, books queue and total cunt of read pages.

        :return: this str.
        """
        return f"Reading log:\n{self.log}\n" \
               f"Books queue:\n{self._str_queue()}\n" \
               f"Processed books:\n{self._str_processed()}"

    def __contains__(self,
                     id_: int) -> bool:
        """
        Whether the queue contains the book at id.

        :param id_: int, book's id.
        :return: bool.
        """
        return bool(self.in_queue(id=id_) + self.in_processed(id=id_))

    def __getitem__(self,
                    id_: int) -> Book:
        if id_ not in self:
            raise IndexError(f"Book with `{id_=}` doesn't exist")

        for book in self.queue + self.processed:
            if book.id == id_:
                return book


def is_ok(num: int or None) -> bool:
    """
    Check that the arg is int > 0.

    :param num: int or None, value to validate.
    :return: bool, whether the arg is int > 0.
    """
    return num is not None and num > 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Books to read, processed books and reading log"
    )
    parser.add_argument(
        '-pl', '--print-log',
        default=False,
        action="store_true",
        dest='pl'
    )
    parser.add_argument(
        '-pq', '--print-queue',
        default=False,
        action="store_true",
        dest='pq'
    )
    parser.add_argument(
        '-pp', '--print-processed',
        default=False,
        action="store_true",
        dest='pp'
    )
    parser.add_argument(
        '-pt', '--print-total',
        default=False,
        action="store_true",
        dest='pt'
    )
    parser.add_argument(
        '-pall', '--print-all',
        default=False,
        action="store_true",
        dest='pall'
    )
    parser.add_argument(
        '-tday', '--today',
        metavar="Set count of read pages for today",
        type=int,
        dest='today',
        required=False
    )
    parser.add_argument(
        '-yday', '--yesterday',
        metavar="Set count of read pages for yesterday",
        type=int,
        dest='yesterday',
        required=False
    )
    parser.add_argument(
        '-cb', '--complete-book',
        default=False,
        action="store_true",
        dest='cb'
    )
    args = parser.parse_args()
    log = Log()
    books_queue = BooksQueue(log)

    if not (args.today is None or args.yesterday is None):
        raise ValueError("Only today or yesterday, not together")

    is_dump_log = False
    if is_ok(args.today):
        log.set_today_log(args.today)
        is_dump_log = True
    elif is_ok(args.yesterday):
        log.set_yesterday_log(args.yesterday)
        is_dump_log = True

    is_dump_books = False
    if args.cb:
        books_queue.complete_book()
        is_dump_books = True

    if args.pall:
        print(books_queue)
    else:
        if args.pl:
            log.print_log()
        if args.pt:
            log.print_total()
        if args.pq:
            books_queue.print_queue()
        if args.pp:
            books_queue.print_processed()

    if is_dump_log:
        log.dump()
    if is_dump_books:
        books_queue.dump()


if __name__ == "__main__":
    main()
