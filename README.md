# ReadingTracker
![Tests status](https://github.com/kunansy/ReadingTracker/actions/workflows/python-app.yml/badge.svg)
![Build Status](https://github.com/kunansy/ReadingTracker/actions/workflows/buildx-docker-image.yml/badge.svg)
![Stable Version](https://img.shields.io/github/v/tag/kunansy/ReadingTracker)
![Latest Release](https://img.shields.io/github/v/release/kunansy/ReadingTracker?color=%233D9970)

## Content
- [What is that](#what-is-that)
- [Installation](#installation)
- [Structure](#structure)
  - [Queue](#queue)
  - [Reading](#reading)
  - [Completed](#completed)
  - [Repeat](#repeat)
  - [Reading log](#reading-log)
  - [Notes](#notes)
  - [System](#system)

## What is that?
The project is expected to help you to read books:
1. Keep a list of books you want to read;
2. Keep a list of reading and completed materials;
3. Calculate statistics;
4. Track the reading log;
5. Take notes to help you remember some important points from the material.

## Installation
1. Clone the repo: `git clone https://github.com/kunansy/ReadingTracker`.
2. Create the Google Drive service account: https://labnol.org/google-api-service-account-220404, first 4 steps.
3. Create env file and fill it: `cp env.template .env`.
4. Run docker container: `docker compose up -d --build --force-recreate`
5. Migrate the database: `docker exec -i -t reading_tracker python3 /app/tracker/main.py`

## Structure
### Queue
Here there are the books, articles, courses etc. to read with some analytics, 
the expected reading time according to the mean pages read.
![Queue](docs/queue.png)

## Reading
Here there are the materials you are currently reading.
![Reading](docs/reading.png)

## Completed
Here there are the materials that have been read.
![Completed](docs/completed.png)

## Repeat
Here there are the materials that have been read and need to be read again, repeated after a month or more.
The priority is equal to the number of months since the material was last read or repeated.
![Repeat](docs/repeat.png)

## Reading log
Here there is the reading log of the materials. The day is red if 
there are less than average pages, green if there are more.
![Reading log](docs/reading_log.png)

## Notes
Here there are notes, the most important info from the materials. 
The user can search a note with Manticoresearch by any text query, 
filter notes by materials or tags.
![Notes](docs/notes.png)

You should:
* Create small notes with one idea in each note.
* Add _tags_ that helps to link some ideas into topic groups: `#health`, `#history`, `#linguistics` etc.
* Add _links_ to help connect notes together using [Zettelkasten method](https://writingcooperative.com/zettelkasten-how-one-german-scholar-was-so-freakishly-productive-997e4e0ca125).
* Each note should be linked to note that has a direct link to it: `[[c2ed0ac7-fe4f-4a23-a00c-8f61d16398ea]]`

## System
Here there are reading graphic, backuping and restoring from the Google Drive.
![System](docs/system.png)
