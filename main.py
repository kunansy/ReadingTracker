#!/usr/bin/env python3

import argparse
import datetime
import logging
from typing import Optional

import matplotlib.pyplot as plt

from src.tracker import Tracker, Log, today, fmt


def is_ok(num: Optional[int]) -> bool:
    """
    Check that the arg is int > 0.

    :param num: value to validate.
    :return: whether the arg is valid.
    """
    return num is not None and num >= 0


def reading_dynamic(log: Log) -> None:
    labels = [
        fmt(date)
        for date in log.dates()
    ]
    values = log.counts()

    plt.xlabel("Dates")
    plt.ylabel("Pages")
    plt.title("Reading dynamic", fontdict={'size': 20})

    plt.plot(labels, values, 'ro-')
    plt.grid()

    step = 4 * (len(log) > 10) + 1
    xt = [
        labels[i]
        for i in range(0, len(labels), step)
    ]
    plt.xticks(xt, rotation="vertical")

    for label, value in zip(labels, values):
        if value == 0:
            continue
        plt.annotate(
            str(value), xy=(label, value),
            xytext=(label, value + 2), fontsize=12
        )
    plt.ylim(-10, log.max[1]['count'] + 10)

    plt.show()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reading tracker: materials to read, "
                    "processed materials and reading log"
    )
    parser.add_argument(
        '-pl', '--print-log',
        help="Print reading log",
        action="store_true",
        dest='pl'
    )
    parser.add_argument(
        '-pr', '--print-reading',
        help="Print materials reading now",
        action="store_true",
        dest='pr'
    )
    parser.add_argument(
        '-pq', '--print-queue',
        help="Print materials queue",
        action="store_true",
        dest='pq'
    )
    parser.add_argument(
        '-pp', '--print-processed',
        help="Print processed materials",
        action="store_true",
        dest='pp'
    )
    parser.add_argument(
        '-pall', '--print-all',
        help="Print all: reading log, materials queue, "
             "processed materials, statistics",
        action="store_true",
        dest='pall'
    )
    parser.add_argument(
        '-tday', '--today',
        help="Set count of pages read today",
        type=int,
        dest='today',
    )
    parser.add_argument(
        '-yday', '--yesterday',
        help="Set count of pages read yesterday",
        type=int,
        dest='yesterday',
    )
    parser.add_argument(
        '-cm', '--complete-material',
        help="Complete material by its id",
        type=int,
        dest='cm'
    )
    parser.add_argument(
        '-rd', '--reading-dynamic',
        help="Show reading dynamic graphic",
        action="store_true",
        dest='rd'
    )
    parser.add_argument(
        '--full-dynamic',
        help="Show full graphic of reading dynamic.",
        action="store_true",
        dest='full'
    )
    args = parser.parse_args()
    sep = '\n' + '_' * 70 + '\n'

    log = Log()
    tracker = Tracker(log)

    if is_ok(args.today):
        log.set_today_log(args.today)
        log.dump()
    if is_ok(args.yesterday):
        log.set_yesterday_log(args.yesterday)
        log.dump()

    if material_id := args.cm:
        try:
            tracker.complete_material(material_id=material_id)
        except ValueError as e:
            logging.error(e)
        except IndexError:
            logging.error(f"Material {material_id=} not found")

    if args.pall:
        print(tracker)
    else:
        if args.pl:
            print("Reading log:")
            print(log, end=sep)
            print("Statistics:")
            print(log.statistics(), end=sep)
        if args.pr:
            print("Reading materials:")
            print(tracker._reading(), end=sep)
        if args.pq:
            print("Materials queue:")
            print(tracker._queue(), end=sep)
        if args.pp:
            print("Processed materials:")
            print(tracker._processed(), end=sep)

    if args.rd:
        if args.full:
            reading_dynamic(log)
        else:
            today_ = today()
            yy, mm = today_.year, today_.month
            month_start = datetime.date(yy, mm, 1)

            reading_dynamic(log[month_start:])


if __name__ == '__main__':
    main()
