# BooksQueue
Reading tracker.

It stores list of books in `data/books.json`, reading log in `data/log.json`.


## Features
It supports:
* Books list: books to read, processed books;
* Reading log.


## Usage
`books.py [-h] [-pl] [-pq] [-pp] [-pt] [-pall] [-tday Set count of read pages 
for today] [-yday Set count of read pages for yesterday] [-cb]`

1. `-h, --help` – see help;
2. `-pl, --print-log` – print log;
3. `-pq, --print-queue` – print books queue;
4. `-pp, --print-processed` – print list of processed books;
5. `-pt, --print-total` – print total count of read pages;   
6. `-pall, --print-all` – print all: log, books queue, processed books, total;
7. `-tday, --today` – set today's reading log;
8. `-yday, --yesterday` – set yesterday's reading log;
9. `-cb, --complete-book` – remove the first book from the queue and add it to
   `processed` list. Set `end_date` as the day when the command is called and 
   `start_day` of the next book in queue as the day after it.
