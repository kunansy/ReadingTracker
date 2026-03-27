# ReadingTracker
![Tests status](https://github.com/kunansy/ReadingTracker/actions/workflows/linters.yml/badge.svg)
![Build Status](https://github.com/kunansy/ReadingTracker/actions/workflows/buildx-docker-image.yml/badge.svg)
![Stable Version](https://img.shields.io/github/v/tag/kunansy/ReadingTracker)
![Latest Release](https://img.shields.io/github/v/release/kunansy/ReadingTracker?color=%233D9970)

## Contents
- [What is this?](#what-is-this)
- [Installation](#installation)
- [Structure](#structure)
  - [Queue](#queue)
  - [Reading](#reading)
  - [Completed](#completed)
  - [Repeat](#repeat)
  - [Reading log](#reading-log)
  - [Notes](#notes)
    - [Notes graph](#notes-graph)
    - [Note context menu](#note-context-menu)
    - [Show the note](#show-the-note)
    - [Edit the note](#edit-the-note)
  - [System](#system)
    - [Material reading graphic](#material-reading-graphic)
    - [Tracker statistics](#tracker-statistics)
    - [Read pages statistics](#read-pages-statistics)
    - [Inserted notes statistics](#inserted-notes-statistics)

## What is this?
ReadingTracker helps you manage your reading workflow:
1. Keep a queue of books/articles/courses you want to read.
2. Track what you’re currently reading and what you’ve finished.
3. Collect reading statistics (pages, streaks, etc.).
4. Maintain a reading log.
5. Take notes and connect them with tags and links (Zettelkasten-style).

## Installation
### Prerequisites
- Docker + Docker Compose (`docker compose`).
- A Google Drive service account is optional (only needed for Drive backup/restore).

### Steps
1. Clone the repo: `git clone https://github.com/kunansy/ReadingTracker`
2. Create the `.env` file: `cp env.template .env`
3. Create the Docker network (required by `docker-compose.yml`): `docker network create tracker-net`
4. Initialize storage (creates DB objects and search indexes): `docker exec -it tracker-app python3 /app/tracker/main.py`

### Optional: Google Drive backup/restore
If you want to use Google Drive backup/restore, create a Google Drive service account and put its JSON credentials into `DRIVE_CREDS` in your `.env`.
The guide below is a good starting point (use the first steps about service accounts):
`https://labnol.org/google-api-service-account-220404`

## Structure
### Queue
This page contains books/articles/courses you plan to read, with basic analytics (for example,
an estimated reading time based on your average pace).
![Queue](docs/queue.png)

## Reading
This page contains materials you are currently reading.
![Reading](docs/reading.png)

## Completed
This page contains materials you’ve finished.
![Completed](docs/completed.png)

## Repeat
This page contains materials you want to reread (typically a month later or more).
The priority equals the number of months since the material was last read/repeated.
![Repeat](docs/repeat.png)

## Reading log
This page shows your reading log. A day is red if you read fewer pages than your average,
and green if you read more.
![Reading log](docs/reading_log.png)

## Notes
This page contains your notes (key ideas from what you read).
You can full-text search via Manticoresearch and filter notes by material or tags.
![Notes](docs/notes.png)

Guidelines:
* Create small notes with one idea in each note.
* Add _tags_ to group related ideas: `#health`, `#history`, `#linguistics`, etc.
* Add _links_ to help connect notes together using [Zettelkasten method](https://writingcooperative.com/zettelkasten-how-one-german-scholar-was-so-freakishly-productive-997e4e0ca125).
* Link notes together using the note ID format: `[[c2ed0ac7-fe4f-4a23-a00c-8f61d16398ea]]`

### Notes graph
This section shows a graph of all notes.
![Notes graph](docs/all_notes_graph.png)

There is also a graph for a selected material.
![Notes graph](docs/material_notes_graph.png)

### Note context menu
You can open a note from the context menu, edit it, or delete it.
![Note context menu](docs/note_context_menu.png)

### Show the note
Use the arrows to iterate through linked notes.
![Open note](docs/open_note.png)

This graph shows links for the current note.
![Note links](docs/note_links.png)

### Edit the note
When editing a note you can:
* Use speech recognition and enter text using a voice (buttons `Start`, `Stop`);
* Select suggested tags (sorted so tags used in this material’s notes come first);
* Add a link to another note (candidates are notes with similar tags, ordered by tag overlap).

Tag and link lists can be scrolled left/right.
![Edit note](docs/edit_note.png)

## System
This page includes charts and system tools (including backup/restore to Google Drive).

All charts show statistics for the selected time span (a week by default).
![System](docs/system.png)

### Material reading graphic
How the material was read over time:
![Reading material graphic](docs/reading_material.png)

### Tracker statistics
![Tracker statistics](docs/tracker_statistics.png)

### Read pages statistics
Read pages statistics for the selected time span.

* `Would be total` — how many pages would be read if there were no empty days;
* A day when a material was completed is marked in green.
![Read pages](docs/read_pages.png)

### Inserted notes statistics
Inserted notes statistics for the selected time span.

![Inserted notes](docs/inserted_notes.png)
