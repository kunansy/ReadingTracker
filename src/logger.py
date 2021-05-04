import sys
import logging
from pathlib import Path


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

logger = logging.getLogger('ReadingTracker')
logger.setLevel(logging.DEBUG)

logger.addHandler(stream_handler)
logger.addHandler(file_handler)


# ---- config for sanic log ----
BASE_MESSAGE_FORMAT = "[%(asctime)s] [%(name)s] [%(levelname)s] " \
                      "[%(module)s:%(funcName)s():%(process)d]"
DATE_FORMAT = "%d-%m-%Y %H:%M:%S"
SANIC_LOG_FILE = LOG_FOLDER / 'sanic.log'

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
        "internalFile": {
            "class": "logging.FileHandler",
            "filename": SANIC_LOG_FILE,
            "formatter": "simple",
            "level": "WARNING"
        },
        "accessStream": {
            "class": "logging.StreamHandler",
            "formatter": "access",
            "level": "DEBUG"
        }
    },
    "loggers": {
        "sanic.root": {
            "level": "DEBUG",
            "handlers": ["internalStream", "internalFile"]
        },
        "sanic.access": {
            "level": "DEBUG",
            "handlers": ["accessStream"]
        },
        "sanic.error": {
            "level": "WARNING",
            "handlers": ["internalFile"]
        }
    }
}
