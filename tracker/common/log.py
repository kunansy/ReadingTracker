import logging

from tracker.common import settings


MSG_FMT = ("{levelname:<8} [{asctime},{msecs:3.0f}] [PID:{process}] "
           "[{filename}:{funcName}():{lineno}] {message}")
DATE_FMT = "%d.%m.%Y %H:%M:%S"

formatter = logging.Formatter(
    fmt=MSG_FMT, datefmt=DATE_FMT, style='{'
)

stream_handler = logging.StreamHandler()
stream_handler.setLevel(settings.LOGGER_LEVEL)
stream_handler.setFormatter(formatter)

logger = logging.getLogger(settings.LOGGER_NAME)
logger.setLevel(settings.LOGGER_LEVEL)

logger.addHandler(stream_handler)
logger.info("Logger configured with level=%s", logger.level)
