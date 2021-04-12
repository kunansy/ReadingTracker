#!/usr/bin/env python3

import argparse
from typing import Optional

import matplotlib.pyplot as plt

from src.tracker import Tracker, Log


def is_ok(num: Optional[int]) -> bool:
    """
    Check that the arg is int > 0.

    :param num: value to validate.
    :return: whether the arg is valid.
    """
    return num is not None and num >= 0


def reading_dynamic(log: Log) -> None:
    labels = log.dates()
    values = log.counts()

    plt.xlabel("Dates")
    plt.ylabel("Pages")
    plt.title("Reading dynamic", fontdict={'size': 20})

    plt.plot(labels, values, 'ro-')
    plt.grid()

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
        help="Print all: reading log, materials queue, "
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
    tracker = Tracker(log)

    if is_ok(args.today):
        log.set_today_log(args.today)
        log.dump()
    if is_ok(args.yesterday):
        log.set_yesterday_log(args.yesterday)
        log.dump()

    if args.cb:
        tracker.complete_material()
        tracker.dump()

    if args.pall:
        print(tracker)
    else:
        if args.pl:
            log.print_log()
        if args.pt:
            log.print_total()
        if args.pq:
            tracker.print_queue()
        if args.pp:
            tracker.print_processed()


if __name__ == '__main__':
    main()
