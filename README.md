# ReadingTracker


## What is that?
The project is expected to help you read books:
1. Keep a list of books to read;
2. Keep a list of reading and completed materials;
3. Calculate statistics;
4. Track the read log;
4. Keep notes to help you remember some important points from the material;
5. Use Janki method to remember notes.


## Data
* Materials to read, reading and completed materials, Notes for them and Cards to recall in `data/materials.db`.
* Reading log: `date: {'count': count, 'material_id': material_id}` in `data/log.json`.

### ERD of the database
```sql
material:
  - material_id SERIAL PRIMARY KEY,
  - title VARCHAR NOT NULL,
  - authors VARCHAR NOT NULL,
  - pages INTEGER NOT NULL,
  - tags VARCHAR;

status:
  - status_id SERIAL PRIMARY KEY,
  - material_id INTEGER REFERENCES(material.material_id) UNIQUE,
  - begin DATE,
  - end DATE;

note:
  - id SERIAL PRIMARY KEY,
  - material_id INTEGER REFERENCES(material.material_id),
  - content TEXT NOT NULL,
  - date DATE NOT NULL,
  - chapter INTEGER NOT NULL,
  - page INTEGER NOT NULL;

card:
  - card_id SERIAL PRIMARY KEY,
  - question TEXT NOT NULL,
  - answer TEXT,
  - date DATE NOT NULL,
  - material_id REFERENCES(material.material_id) NOT NULL,
  - note_id REFERENCES(note.id);

recall:
  - recall_id SERIAL PRIMARY KEY,
  - card_id REFERENCES(card.card_id) NOT NULL,
  - last_repeat_date DATE NOT NULL,
  - next_repeat_date DATE NOT NULL,
  - mult FLOAT NOT NULL;
```

## Config
All params are in environ:
1. `LOGGER_NAME` – name of the main logger;
2. `LOGGER_LEVEL` – level of the main logger `DEBUG` by default;
3. `SANIC_LOGGER_LEVEL` – `DEBUG` by default;
4. `READ_PER_DAY` – expected count of pages read a day, 50 by default;
5. `CARDS_PER_DAY` – count of cards to repeat a day, 25 by default;
6. `WORKERS` – count of ASGI workers, 1 by default;
7. `SANIC_ACCESS` – write access log or not, not by default;
8. `DB_URI` – path to the database;
9. `DEBUG` – use debug mode or not, not by default.


## Usage
### WEB
```shell
. venv/bin/activate
./server.py
```
