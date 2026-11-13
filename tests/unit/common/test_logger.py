import logging

import pytest

from tracker.common import (
    logger as package_logger,
    settings,
)
from tracker.common.logger import (
    DATE_FMT,
    MSG_FMT,
    EndpointLogsFilter,
    formatter,
    logger,
    stream_handler,
)


def _record(msg: str, *args: object) -> logging.LogRecord:
    return logging.LogRecord(
        name="gunicorn.access",
        level=logging.INFO,
        pathname="glogging.py",
        lineno=1,
        msg=msg,
        args=args,
        exc_info=None,
    )


@pytest.mark.parametrize(
    ("message", "is_kept"),
    [
        ('"GET /metrics HTTP/1.1" 200', False),
        ('"GET /metrics/ HTTP/1.1" 200', False),
        ('"GET /api/metrics HTTP/1.1" 200', False),
        ('"GET /materials HTTP/1.1" 200', True),
        ('"GET /METRICS HTTP/1.1" 200', True),
        ("metrics", True),
        ("", True),
    ],
    ids=[
        "exact-path",
        "trailing-slash",
        "path-as-substring",
        "other-path",
        "case-sensitive",
        "no-leading-slash",
        "empty-message",
    ],
)
def test_endpoint_filter_drops_records_mentioning_the_path(message, is_kept):
    log_filter = EndpointLogsFilter(endpoint="/metrics")

    assert log_filter.filter(_record(message)) is is_kept


def test_endpoint_filter_looks_at_the_formatted_message():
    log_filter = EndpointLogsFilter(endpoint="/readiness")

    assert log_filter.filter(_record('"GET %s HTTP/1.1" %d', "/readiness", 200)) is False
    assert log_filter.filter(_record('"GET %s HTTP/1.1" %d', "/notes", 200)) is True


def test_endpoint_filter_with_empty_path_drops_everything():
    log_filter = EndpointLogsFilter(endpoint="")

    assert log_filter.filter(_record("anything")) is False


def test_endpoint_filter_passes_name_to_base_filter():
    log_filter = EndpointLogsFilter("/metrics", "gunicorn")

    assert log_filter.name == "gunicorn"


def test_logger_is_configured_from_settings():
    assert logger.name == "ReadingTrackerTests"
    assert logger.name == settings.LOGGER_NAME
    assert logger.level == logging.DEBUG
    assert logger is logging.getLogger("ReadingTrackerTests")


def test_package_exports_the_logger_object():
    assert package_logger is logger


def test_logger_writes_to_the_stream_handler_once():
    assert logger.handlers.count(stream_handler) == 1
    assert stream_handler.level == logging.DEBUG
    assert stream_handler.formatter is formatter


def test_formatter_output():
    record = logging.LogRecord(
        name="ReadingTrackerTests",
        level=logging.WARNING,
        pathname="/app/tracker/main.py",
        lineno=42,
        msg="Привет, %s",
        args=("мир",),
        exc_info=None,
        func="handler",
    )
    record.created = 0
    record.msecs = 7
    record.process = 123

    formatted = formatter.format(record)

    # only the date part: the hour of `created` depends on the local timezone
    assert formatted.startswith("WARNING  [01.01.1970 ")
    assert formatted.endswith(",  7] [PID:123] [main.py:handler():42] Привет, мир")
    assert formatter._fmt == MSG_FMT
    assert formatter.datefmt == DATE_FMT == "%d.%m.%Y %H:%M:%S"


def test_gunicorn_access_log_skips_metrics_and_readiness():
    access_logger = logging.getLogger("gunicorn.access")

    paths = sorted(
        log_filter._path
        for log_filter in access_logger.filters
        if isinstance(log_filter, EndpointLogsFilter)
    )

    assert paths == ["/metrics", "/readiness"]


@pytest.mark.parametrize(
    ("path", "is_logged"),
    [("/metrics", False), ("/readiness", False), ("/materials", True)],
)
def test_gunicorn_access_logger_filters_records(path, is_logged):
    access_logger = logging.getLogger("gunicorn.access")

    assert bool(access_logger.filter(_record(f'"GET {path} HTTP/1.1" 200'))) is is_logged
