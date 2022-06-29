# ReadingTracker
![Tests status](https://github.com/kunansy/ReadingTracker/actions/workflows/python-app.yml/badge.svg)
![Build Status](https://github.com/kunansy/ReadingTracker/actions/workflows/buildx-docker-image.yml/badge.svg)
![Stable Version](https://img.shields.io/github/v/tag/kunansy/ReadingTracker)
![Latest Release](https://img.shields.io/github/v/release/kunansy/ReadingTracker?color=%233D9970)

## Content
- [What is that](#what-is-that)
- [Structure](#structure)
  - [Queue](#queue)
  - [Reading](#reading)
  - [Completed](#completed)
  - [Repeat](#repeat)
  - [Reading log](#reading-log)
  - [Notes](#notes)
  - [System](#system)

## What is that?
The project is expected to help one read books:
1. Keep a list of books to read;
2. Keep a list of reading and completed materials;
3. Calculate statistics;
4. Track the reading log;
4. Keep notes to help remember some important points from the material.

## Structure
### Queue
Here there are the books, articles, courses etc to read with some analytics, 
expected reading duration according to the average read pages.
![Queue](docs/queue.png)

## Reading
Here there are the materials that are currently being read.
![Reading](docs/reading.png)

## Completed
Here there are the materials that have been read.
![Completed](docs/completed.png)

## Repeat
Here there are the materials that have been read and need to be read again, repeat them after a month or more.
Priority is equal to the number of month since the material was read or repeated the last time.
![Repeat](docs/repeat.png)

## Reading log
Here there are the reading log of the materials. The day is red if 
there are less than average pages, green if there are more.
![Reading log](docs/reading_log.png)

## Notes
Here there are the notes, the most important info from the materials.
![Notes](docs/notes.png)

## System
Here there are reading graphic, backuping and restoring from the Google Drive.
![System](docs/system.png)

