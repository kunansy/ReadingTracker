# ReadingTracker

It stores list of materials to read in `data/tracker.db`, reading log in `data/log.json`.


## Usage
`usage: main.py [-h] [-pl] [-pr] [-pq] [-pp] [-pall] [-tday TODAY] [-yday YESTERDAY] [-cm CM] [-rd]`

Optional arguments:
1. `-h, --help`                      Show this help message and exit
1. `-pl, --print-log`                Print reading log
1. `-pr, --print-reading`            Print materials reading now
1. `-pq, --print-queue`              Print materials queue
1. `-pp, --print-processed`          Print processed materials
1. `-pall, --print-all`              Print all: reading log, materials queue, processed materials, statistics
1. `-tday COUNT, --today COUNT`      Set count of pages read today
1. `-yday COUNT, --yesterday COUNT`  Set count of pages read yesterday
1. `-cm CM, --complete-material CM`  Complete material by its id
1. `-rd, --reading-dynamic`          Show reading dynamic graphic
