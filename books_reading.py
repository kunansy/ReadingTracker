#!/usr/bin/env python3
import argparse
import csv
import datetime
from pathlib import Path
from typing import Dict

import pymorphy2
import ujson

DATA_FOLDER = Path('data')

BOOKS_QUEUE_PATH = DATA_FOLDER / 'book_queue.csv'
LOG_PATH = DATA_FOLDER / 'log.json'

PAGES_PER_DAY = 50
START_DATE = datetime.date(2020, 12, 12)

DATE_FORMAT = '%d.%m.%Y'

morph = pymorphy2.MorphAnalyzer()


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


def get_log(path: Path = LOG_PATH) -> Dict[datetime.date, int]:
    """ Get log from the file and parse it to JSON dict.
    Convert keys to datetime.date, values to int.

    :param path: Path to the log file.
    :return: JSON dict with the format.
    :exception ValueError: if the file if empty.
    """
    with path.open(encoding='utf-8') as f:
        data = ujson.loads(f.read())

    res = {}
    for date, count in data.items():
        date = datetime.datetime.strptime(date, DATE_FORMAT)
        res[date] = count

    return data


def dump_log(data, path: Path = LOG_PATH) -> None:
    """ Dump dict to the log file.

    :param data: dict to dump.
    :param path: Path to the log file.
    :return: None.
    """
    with path.open('w', encoding='utf-8') as f:
        data_str = {}
        for date, count in data.items():
            try:
                date = date.strftime(DATE_FORMAT)
            except AttributeError:
                pass
            data_str[date] = count
        ujson.dump(data_str, f, indent=4)


def today() -> datetime.date:
    """ Get today.

    :return: datetime.date, today.
    """
    return datetime.date.today()


def get_books(path: Path = BOOKS_QUEUE_PATH) -> Dict:
    """

    :param path: path to book queue file.
    :return: book queue.
    """
    books = {}
    with path.open(encoding='utf-8', newline='') as f:
        reader = csv.reader(f, delimiter='\t')
        for name, pages in reader:
            books[name] = {
                'pages': int(pages),
            }
        return books


def print_queue(books: Dict,
                avg: int = PAGES_PER_DAY) -> None:
    """ Print books queue.

    :param books: dict, books queue.
    :param avg: int, average count of read pages.
    :return: None.
    """
    last_date = START_DATE
    for key, val in books.items():
        days_count = val['pages'] // avg + 1
        finish_date = last_date + datetime.timedelta(days=days_count)

        days = f"{days_count} {with_num('день', days_count)}"
        print(f"«{key}» будет прочитана за {days}")

        start = last_date.strftime(DATE_FORMAT)
        stop = finish_date.strftime(DATE_FORMAT)
        print(f"С {start} по {stop}")
        print()

        last_date = finish_date + datetime.timedelta(days=1)


def get_avg(log: Dict) -> int:
    """ Get average count of read pages.

    :param log:
    :return: int, average count of read pages.
    """
    try:
        return sum(log.values()) // len(log)
    except ZeroDivisionError:
        return 0


def print_log(log: Dict) -> None:
    """ Print log.

    :param log: dict, log data.
    :return: None.
    """
    sum_ = 0
    for date, read_pages in log.items():
        print(f"{date}: {read_pages} "
              f"{with_num('страница', read_pages)}")
        sum_ += read_pages
    print()

    avg = get_avg(log)
    print(f"В среднем {avg} {with_num('страница', avg)}")

    print("Это ", end='')
    diff = abs(PAGES_PER_DAY - avg)
    if avg == PAGES_PER_DAY:
        print('равно ожидаемому среднему значению')
    elif avg < PAGES_PER_DAY:
        print(f'на {diff} меньше ожидаемого среднего значения')
    else:
        print(f'на {diff} больше ожидаемого среднего значения')


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
        '-pall', '--print-all',
        default=False,
        action="store_true",
        dest='pall'
    )
    parser.add_argument(
        '-tday', '--today',
        type=int,
        dest='today',
        required=False
    )
    parser.add_argument(
        '-yday', '--yesterday',
        type=int,
        dest='yesterday',
        required=False
    )
    parser.add_argument(
        '-tdayc', '--todayc',
        metavar='Calculate how many pages was read today '
                'accorging to the last read page number',
        type=int,
        dest='todayc',
        required=False
    )
    parser.add_argument(
        '-ydayc', '--yesterdayc',
        metavar='Calculate how many pages was read yesterday '
                'accorging to the last read page number',
        type=int,
        dest='yesterdayc',
        required=False
    )
    args = parser.parse_args()

    try:
        log = get_log()
    except ValueError:
        log = {}

    avg = get_avg(log) or 1
    books = get_books()

    if args.pl:
        print_log(log)
    if args.pq:
        print_queue(books, avg)
    if args.pall:
        print(sum(log.values()))

    if not (args.today is None or args.yesterday is None):
        raise ValueError("Only today or yesterday, not together")
    if not (args.todayc is None or args.yesterdayc is None):
        raise ValueError("Only todayc or yesterdayc, not together")
    if not (args.today is None or args.todayc is None):
        raise ValueError("Only -c or -, not together")

    if is_ok(args.today):
        log[today()] = args.today
    elif is_ok(args.yesterday):
        log[today() - datetime.timedelta(days=1)] = args.yesterday

    even_read = sum(log.values())
    if is_ok(args.todayc):
        assert args.todayc >= even_read, 'Last page num must be > even read'
        log[today()] = args.todayc - even_read
    elif is_ok(args.yesterdayc):
        assert args.yesterdayc >= even_read, 'Last page num must be > even read'
        log[today() - datetime.timedelta(days=1)] = args.yesterdayc - even_read
    dump_log(log)


if __name__ == "__main__":
    main()

