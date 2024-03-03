import os
from pathlib import Path

import orjson
from environs import Env
from marshmallow.validate import OneOf


env = Env()
env.read_env()

DATE_FORMAT = "%Y-%m-%d"
DATETIME_FORMAT = f"{DATE_FORMAT} %H:%M:%S"

DSN_TEMPLATE = "postgresql+asyncpg://{username}:{password}@{host}:{port}/{db_name}"

API_VERSION = "0.1.0"
if (version_file := Path("VERSION")).exists():
    API_VERSION = version_file.read_text().strip()

DATA_DIR = Path("data/")
DATA_DIR.mkdir(parents=True, exist_ok=True)

TRACKER_URL = env(
    "TRACKER_URL",
    "http://tracker-app:8000",
    validate=lambda url: not url.endswith("/"),
)

with env.prefixed("CACHE_"):
    _CACHE_URL = env("URL", "redis://tracker-cache")
    _CACHE_PORT = env.int("PORT", 6379)
    CACHE_PASSWORD = env("PASSWORD")

CACHE_URL = f"{_CACHE_URL}:{_CACHE_PORT}"

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


with env.prefixed("YOUTUBE_API_"):
    YOUTUBE_API_URL = env.url("URL", "https://youtube.googleapis.com/youtube/v3/videos")
    YOUTUBE_API_KEY = env("KEY")

path = os.environ.get("PATH")
metrics_dir = os.environ.get("PROMETHEUS_MULTIPROC_DIR")

os.environ.clear()

if path:
    os.environ["PATH"] = path
if metrics_dir:
    os.environ["PROMETHEUS_MULTIPROC_DIR"] = metrics_dir
