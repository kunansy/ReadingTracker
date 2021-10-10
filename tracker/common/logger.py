import logging
import sys
from pathlib import Path

from src import settings


MSG_FMT = "[{asctime},{msecs:3.0f}] [{name}] [{levelname:^8}] " \
          "[{module}:{funcName}] [{process}] {message}"
DATE_FMT = "%d-%m-%Y %H:%M:%S"
LOG_FOLDER = Path('./logs')
LOG_FILE = LOG_FOLDER / 'tracker.log'

LOG_FOLDER.mkdir(exist_ok=True)

formatter = logging.Formatter(
    fmt=MSG_FMT, datefmt=DATE_FMT, style='{'
)

stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.DEBUG)
stream_handler.setFormatter(formatter)

file_handler = logging.FileHandler(
    LOG_FILE, delay=True
)
file_handler.setLevel(logging.WARNING)
file_handler.setFormatter(formatter)

logger = logging.getLogger(settings.LOGGER_NAME)
logger.setLevel(settings.LOGGER_LEVEL)

logger.addHandler(stream_handler)
logger.addHandler(file_handler)


# ---- config for sanic log ----
BASE_MESSAGE_FORMAT = "[%(asctime)s] [%(name)s] [%(levelname)s] " \
                      "[%(module)s:%(funcName)s():%(process)d]"
DATE_FORMAT = "%d-%m-%Y %H:%M:%S"
SANIC_LOG_FILE = LOG_FOLDER / 'sanic.log'
SANIC_ERROR_LOG_FILE = LOG_FOLDER / 'sanic_error.log'
SANIC_ACCESS_LOG_FILE = LOG_FOLDER / 'access.log'

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {
            "format": f"{BASE_MESSAGE_FORMAT} %(message)s",
            "datefmt": DATE_FORMAT
        },
        "access": {
            "format": f"{BASE_MESSAGE_FORMAT} %(request)s, "
                      f"status: %(status)s, size: %(byte)sb",
            "datefmt": DATE_FORMAT
        }
    },
    "handlers": {
        "internalStream": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
            "stream": sys.stderr,
            "level": "DEBUG"
        },
        "errorFile": {
            "class": "logging.FileHandler",
            "filename": SANIC_ERROR_LOG_FILE,
            "formatter": "simple",
            "level": "WARNING"
        },
        "accessStream": {
            "class": "logging.StreamHandler",
            "formatter": "access",
            "level": "DEBUG"
        },
        "accessFile": {
            "class": "logging.FileHandler",
            "filename": SANIC_ACCESS_LOG_FILE,
            "formatter": "access",
            "level": "DEBUG"
        }
    },
    "loggers": {
        "sanic.root": {
            "level": logging.DEBUG,
            "handlers": ["internalStream"]
        },
        "sanic.access": {
            "level": "DEBUG",
            "handlers": ["accessStream", "accessFile"]
        },
        "sanic.error": {
            "level": "WARNING",
            "handlers": ["errorFile"]
        }
    }
}
