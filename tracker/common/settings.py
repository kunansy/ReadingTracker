import os
from pathlib import Path

from environs import Env


env = Env()
env.read_env()

DATE_FORMAT = '%d-%m-%Y'
DATA_FOLDER = Path('data')

with env.prefixed("DB_"):
    DB_HOST = env("HOST")
    DB_PORT = env.int("PORT")
    DB_NAME = env("NAME")
    DB_USER = env("USER")
    DB_PASSWORD = env("PASSWORD")

with env.prefixed("LOGGER_"):
    LOGGER_NAME = env("NAME")
    LOGGER_LEVEL = env.log_level("LEVE")

with env.prefixed("PER_DAY_"):
    PAGES_PER_DAY = env.int('PER_DAY_PAGES', 50)
    # max count of cards repeated per day
    _MAX_PER_DAY = env.int('PER_DAY_CARDS', 25)

os.environ.clear()
