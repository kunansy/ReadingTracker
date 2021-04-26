import sys


BASE_MESSAGE_FORMAT = "[%(asctime)s] [%(name)s:%(levelname)s] " \
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
