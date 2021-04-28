import sys
import logging


MSG_FMT = "[{asctime},{msecs:3.0f}] [{name}] [{levelname:^8}] " \
          "[{module}:{funcName}] [{process}] {message}"
DATE_FMT = "%d-%m-%Y %H:%M:%S"

formatter = logging.Formatter(
    fmt=MSG_FMT, datefmt=DATE_FMT, style='{')

stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.DEBUG)
stream_handler.setFormatter(formatter)

logger = logging.getLogger('ReadingTracker')
logger.setLevel(logging.DEBUG)

logger.addHandler(stream_handler)


# ---- config for sanic log ----
BASE_MESSAGE_FORMAT = "[%(asctime)s] [%(name)s] [%(levelname)s] " \
                      "[%(module)s:%(funcName)s():%(process)d]"
DATE_FORMAT = "%d-%m-%Y %H:%M:%S"

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
        "accessStream": {
            "class": "logging.StreamHandler",
            "formatter": "access",
            "level": "DEBUG"
        }
    },
    "loggers": {
        "sanic.root": {
            "level": "DEBUG",
            "handlers": ["internalStream"]
        },
        "sanic.access": {
            "level": "DEBUG",
            "handlers": ["accessStream"]
        }
    }
}
