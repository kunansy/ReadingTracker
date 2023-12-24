import os
from pathlib import Path

import orjson
from environs import Env
from marshmallow.validate import OneOf


env = Env()
env.read_env()

DATE_FORMAT = "%d-%m-%Y"
DATETIME_FORMAT = f"{DATE_FORMAT} %H:%M:%S"

DSN_TEMPLATE = "postgresql+asyncpg://{username}:{password}@{host}:{port}/{db_name}"

API_VERSION = "0.1.0"
if (version_file := Path("VERSION")).exists():
    API_VERSION = version_file.read_text().strip()

DATA_DIR = Path("data/")
DATA_DIR.mkdir(parents=True, exist_ok=True)

with env.prefixed("CACHE_"):
    CACHE_URL = env("URL", "redis://tracker-cache")
    CACHE_PASSWORD = env("CACHE_PASSWORD")

with env.prefixed("API_"):
    API_DEBUG = env.bool("DEBUG", False)

with env.prefixed("DB_"):
    DB_HOST = env("HOST")
    DB_PORT = env.int("PORT")
    DB_NAME = env("NAME")
    DB_USERNAME = env("USERNAME")
    DB_PASSWORD = env("PASSWORD")

    DB_TIMEOUT = env.int("TIMEOUT", 5)
    DB_ISOLATION_LEVEL = env(
        "ISOLATION_LEVEL",
        "REPEATABLE READ",
        validate=OneOf(
            ["READ UNCOMMITTED", "READ COMMITTED", "REPEATABLE READ", "SERIALIZABLE"],
            error="invalid isolation level",
        ),
    )

DB_URI = DSN_TEMPLATE.format(
    username=DB_USERNAME,
    password=DB_PASSWORD,
    host=DB_HOST,
    port=DB_PORT,
    db_name=DB_NAME,
)

with env.prefixed("LOGGER_"):
    LOGGER_NAME = env("NAME", "ReadingTracker")
    LOGGER_LEVEL = env.log_level("LEVEL", "debug")

with env.prefixed("DRIVE_"):
    DRIVE_CREDS = orjson.loads(env("CREDS"))

with env.prefixed("MANTICORE_MYSQL_"):
    MANTICORE_MYSQL_HOST = env("HOST")
    MANTICORE_MYSQL_PORT = env.int("PORT", 9306)
    MANTICORE_MYSQL_DB_NAME = env("DB_NAME", "Manticore")

with env.prefixed("BACKUP_"):
    BACKUP_HOST = env("HOST")
    BACKUP_PORT = env.int("PORT")
    BACKUP_TARGET = f"{BACKUP_HOST}:{BACKUP_PORT}"

path = os.environ.get("PATH")
os.environ.clear()

if path:
    os.environ["PATH"] = path
