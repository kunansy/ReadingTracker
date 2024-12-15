import logging

from tracker.common import settings


MSG_FMT = (
    "{levelname:<8} [{asctime},{msecs:3.0f}] [PID:{process}] "
    "[{filename}:{funcName}():{lineno}] {message}"
)
DATE_FMT = "%d.%m.%Y %H:%M:%S"

formatter = logging.Formatter(fmt=MSG_FMT, datefmt=DATE_FMT, style="{")

stream_handler = logging.StreamHandler()
stream_handler.setLevel(settings.LOGGER_LEVEL)
stream_handler.setFormatter(formatter)

logger = logging.getLogger(settings.LOGGER_NAME)
logger.setLevel(settings.LOGGER_LEVEL)

logger.addHandler(stream_handler)
logger.info("Logger configured with level=%s", logger.level)


class EndpointLogsFilter(logging.Filter):
    def __init__(self, endpoint: str, *args, **kwargs):  # noqa: ANN002
        super().__init__(*args, **kwargs)
        self._path = endpoint

    def filter(self, record: logging.LogRecord) -> bool:
        return record.getMessage().find(self._path) == -1


logging.getLogger("uvicorn.access").addFilter(EndpointLogsFilter(endpoint="/metrics"))
logging.getLogger("uvicorn.access").addFilter(EndpointLogsFilter(endpoint="/readiness"))
