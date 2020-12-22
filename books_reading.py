#!/usr/bin/env python3
import argparse
import datetime
from pathlib import Path
from typing import Dict, List, Iterator

import pymorphy2
import ujson

morph = pymorphy2.MorphAnalyzer()
DATE_FORMAT = '%d.%m.%Y'


def with_num(word: str, num: int) -> str:
    """
    Make the word agree with the number.
    If it is not possible return the word.

    :param word: str, Russian word to make agree with the number.
    :param num: int, num to which the word will be agreed.
    :return: str, agreed with the number word if it's possible.
    """
    try:
        word = morph.parse(word)[0]
    except AttributeError:
        return word
    word = word.make_agree_with_number(num)
    return word.word


def inflect_word(word: str):
    def wrapped(num: int) -> str:
        return with_num(word, num)

    return wrapped


class Book:
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
        try:
            date = datetime.datetime.strptime(date, DATE_FORMAT)
            date = date.date()
        except TypeError:
            pass
        except ValueError:
            raise ValueError(f"Wrong date format '{date=}'")

        self.__start_date = date

    @end_date.setter
    def end_date(self,
                 date: datetime.date or str) -> None:
        """
        :param date: datetime.date or str, new end_date value.
        :return: None.

        :exception ValueError: if the date is str with wrong format.
        """
        try:
            date = datetime.datetime.strptime(date, DATE_FORMAT)
            date = date.date()
        except TypeError:
            pass
        except ValueError:
            raise ValueError(f"Wrong date format '{date=}'")

        self.__end_date = date

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
    DATA_FOLDER = Path('data')

    BOOKS_QUEUE_PATH = DATA_FOLDER / 'book_queue.csv'
    LOG_PATH = DATA_FOLDER / 'log.json'

    PAGES_PER_DAY = 50

    def __init__(self) -> None:
        self.__books = self._get_books()
        try:
            log = self._get_log()
        except ValueError:
            log = {}
        self.__log = log
        self.inflect_page = inflect_word('страница')
        self.inflect_day = inflect_word('день')

    @property
    def log(self) -> dict:
        """
        Get reading log.

        :return: dict, reading log.
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
    def avg(self) -> int:
        """ Get average count of read pages.

        :return: int, average count of read pages.
        """
        try:
            return sum(self.log.values()) // len(self.log)
        except ZeroDivisionError:
            return 0

    @property
    def total(self) -> int:
        """
        :return: int, total count read pages.
        """
        return sum(self.log.values())

    @property
    def today(self) -> datetime.date:
        """ Get today.

        :return: datetime.date, today.
        """
        return datetime.date.today()

    @property
    def yesterday(self) -> datetime.date:
        """ Get yesterday.

        :return: datetime.date, yesterday.
        """
        return self.today - datetime.timedelta(days=1)

    @property
    def start_date(self) -> datetime.date:
        """
        :return: datetime.date, date when reading
         of the first book started.
        """
        return self[1].start_date

    def _set_log(self,
                 date: datetime.date or str,
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

        try:
            date = datetime.datetime.strptime(date, DATE_FORMAT)
            date = date.date()
        except TypeError:
            pass
        except ValueError as e:
            raise ValueError(f"Wrong date format\n{e}")

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
        self._set_log(self.today, pages)

    def set_yesterday_log(self,
                          pages: int) -> None:
        """
        Set yesterday's reading log.

        :param pages: int, count of pages read yesterday.
        :return: None.
        """
        self._set_log(self.yesterday, pages)

    def _get_log(self) -> Dict[datetime.date, int]:
        """ Get log from the file and parse it to JSON dict.
        Convert keys to datetime.date, values to int.

        :return: JSON dict with the format.
        :exception ValueError: if the file if empty.
        """
        with self.LOG_PATH.open(encoding='utf-8') as f:
            data = ujson.loads(f.read())

        res = {}
        for date, count in data.items():
            date = datetime.datetime.strptime(date, DATE_FORMAT)
            res[date.date()] = count

        return res

    def _dump_log(self) -> None:
        """ Dump dict to the log file.

        :return: None.
        """
        with self.LOG_PATH.open('w', encoding='utf-8') as f:
            data_str = {}
            for date, count in self.log.items():
                data_str[date.strftime(DATE_FORMAT)] = count
            ujson.dump(data_str, f, indent=4)

    def _get_books(self) -> dict:
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

    def _dump_books(self) -> None:
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
            ujson.dump(res, f, indent=2, ensure_ascii=False)

    def _str_queue(self) -> str:
        """ Convert books queue to str to print.

        :return: this str.
        """
        res = ''

        last_date = self.START_DATE
        for key, val in self.books.items():
            days_count = val['pages'] // self.avg + 1
            finish_date = last_date + datetime.timedelta(days=days_count)

            days = f"{days_count} {self.inflect_day(days_count)}"
            res += f"«{key}» будет прочитана за {days}\n"

            start = last_date.strftime(DATE_FORMAT)
            stop = finish_date.strftime(DATE_FORMAT)
            res += f"С {start} по {stop}\n\n"

            last_date = finish_date + datetime.timedelta(days=1)
        return f"{res.strip()}\n{'-' * 70}"

    def _str_log(self) -> str:
        """ Convert log to str to print.

        :return: this str.
        """
        res = ''
        sum_ = 0

        for date, read_pages in self.log.items():
            date = date.strftime(DATE_FORMAT)
            res += f"{date}: {read_pages} " \
                   f"{self.inflect_page(read_pages)}\n"
            sum_ += read_pages
        res += '\n'

        avg = self.avg
        res += f"В среднем {avg} {self.inflect_page(avg)}\n"

        res += "Это "
        diff = abs(self.PAGES_PER_DAY - avg)
        if avg == self.PAGES_PER_DAY:
            res += "равно ожидаемому среднему значению"
        elif avg < self.PAGES_PER_DAY:
            res += f"на {diff} меньше ожидаемого среднего значения"
        else:
            res += f"на {diff} больше ожидаемого среднего значения"

        return f"{res}\n{'-' * 70}"

    def _str_total(self) -> str:
        """
        Get total count of read pages to print.

        :return: this str.
        """
        return f"Всего прочитано {self.total} " \
               f"{self.inflect_page(self.total)}\n" \
               f"{'-' * 70}"

    def print_queue(self) -> None:
        """
        Print books queue.

        :return: None.
        """
        print(self._str_queue())

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

    def __str__(self) -> str:
        """
        Get log, books queue and total cunt of read pages.

        :return: this str.
        """
        return f"{self._str_log()}\n\n" \
               f"{self._str_queue()}\n\n" \
               f"{self._str_total()}"

    def __del__(self) -> None:
        """
        Dump reading log and delete the object.

        :return: None.
        """
        self._dump_log()
        del self


def is_ok(num: int or None) -> bool:
    """
    Check that the arg is int > 0.

    :param num: int or None, value to validate.
    :return: bool, whether the arg is int > 0.
    """
    return num is not None and num > 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Books queue"
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
        metavar="Set count of read page for today",
        type=int,
        dest='today',
        required=False
    )
    parser.add_argument(
        '-yday', '--yesterday',
        metavar="Set count of read page for yesterday",
        type=int,
        dest='yesterday',
        required=False
    )
    args = parser.parse_args()
    books_queue = BooksQueue()

    if not (args.today is None or args.yesterday is None):
        raise ValueError("Only today or yesterday, not together")

    if is_ok(args.today):
        books_queue.set_today_log(args.today)
    elif is_ok(args.yesterday):
        books_queue.set_yesterday_log(args.yesterday)

    if args.pall:
        print(books_queue)
    else:
        if args.pl:
            books_queue.print_log()
        if args.pq:
            books_queue.print_queue()
        if args.pt:
            books_queue.print_total()


if __name__ == "__main__":
    main()
