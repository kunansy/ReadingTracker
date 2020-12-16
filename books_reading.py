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


def get_books(path: Path = BOOKS_QUEUE_PATH,
              avg: int = PAGES_PER_DAY) -> Dict:
    """

    :param path: path to book queue file.
    :param avg: int, average count of read pages.
    :return: book queue.
    """
    books = {}
    with path.open(encoding='utf-8') as f:
        reader = csv.reader(f, delimiter=';')

        last_date = START_DATE
        for name, pages in reader:
            pages = int(pages)
            how_long = pages // avg + 1
            date = last_date + datetime.timedelta(days=how_long)

            books[name] = {
                'pages': pages,
                'start': last_date,
                'stop': date,
                'days': how_long
            }
            last_date = date + datetime.timedelta(days=1)

        return books


def print_queue(books: Dict) -> None:
    """ Print books queue.

    :param books: dict, books queue.
    :return: None.
    """
    for key, val in books.items():
        days_count = val['days']
        days = f"{days_count} {with_num('день', days_count)}"
        print(f"«{key}» будет прочитана за {days}")
        start = val['start'].strftime(DATE_FORMAT)
        stop = val['stop'].strftime(DATE_FORMAT)
        print(f"С {start} по {stop}")
        print()


def get_avg(log: Dict) -> int:
    """ Get average count of read pages.

    :param log:
    :return: int, acerage count of read pages.
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
        '--today',
        type=int,
        dest='today',
        required=False
    )
    parser.add_argument(
        '--yesterday',
        type=int,
        dest='yesterday',
        required=False
    )

    args = parser.parse_args()

    try:
        log = get_log()
    except ValueError:
        log = {}

    avg = get_avg(log) or 1

    if args.pl:
        print_log(log)
    if args.pq:
        books = get_books(avg=avg)
        print_queue(books)

    if not (args.today is None or args.yesterday is None):
        raise ValueError("Only today or yesterday, not together")

    if args.today is not None:
        log[today()] = args.today
    if args.yesterday is not None:
        log[today() - datetime.timedelta(days=1)] = args.yesterday

    dump_log(log)


if __name__ == "__main__":
    main()
