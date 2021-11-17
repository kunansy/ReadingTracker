import os

from environs import Env


env = Env()
env.read_env()

DATE_FORMAT = '%d-%m-%Y'
DSN_TEMPLATE = "postgresql+asyncpg://{username}:{password}" \
               "@{host}:{port}/{db_name}"

with env.prefixed("API_"):
    API_PORT = env.int("PORT")
    API_DEBUG = env.bool("DEBUG", False)
    API_VERSION = env("VERSION")

with env.prefixed("DB_"):
    DB_HOST = env("HOST")
    DB_PORT = env.int("PORT")
    DB_NAME = env("NAME")
    DB_USERNAME = env("USERNAME")
    DB_PASSWORD = env("PASSWORD")

DB_URI = DSN_TEMPLATE.format(
    username=DB_USERNAME,
    password=DB_PASSWORD,
    host=DB_HOST,
    port=DB_PORT,
    db_name=DB_NAME
)

with env.prefixed("LOGGER_"):
    LOGGER_NAME = env("NAME", "ReadingTracker")
    LOGGER_LEVEL = env.log_level("LEVEL", 'debug')

with env.prefixed("PER_DAY_"):
    PAGES_PER_DAY = env.int('PER_DAY_PAGES', 50)
    # max count of cards repeated per day
    _MAX_PER_DAY = env.int('PER_DAY_CARDS', 25)

os.environ.clear()
