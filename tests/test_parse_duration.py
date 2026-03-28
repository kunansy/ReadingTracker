import pytest

from tracker.materials.db import _parse_duration


@pytest.mark.parametrize(
    ("iso_duration", "expected_minutes"),
    [
        # zero / empty
        ("", 0),
        ("   ", 0),
        ("PT", 0),
        ("PT0S", 0),
        ("PT0H0M0S", 0),
        # seconds only
        ("PT59S", 1),
        ("PT30S", 0),  # 0.5 min — Python rounds half to even
        ("PT31S", 1),
        ("PT1S", 0),
        # minutes only
        ("PT2M", 2),
        ("PT1M", 1),
        ("PT0M", 0),
        # hours only
        ("PT1H", 60),
        ("PT10H", 600),
        # combined (YouTube-style)
        ("PT1H2M3S", 62),
        ("PT1H30M", 90),
        ("PT1H0M0S", 60),
        ("PT0H1M0S", 1),
        ("PT1M30S", 2),
        ("PT5M30S", 6),
        ("PT4M13S", 4),  # 253 s → 4.216… min → 4
        # long (615.5 min → half-to-even → 616)
        ("PT10H15M30S", 616),
        # optional components omitted (regression vs naive string-split parser)
        ("PT2M0S", 2),
        ("PT0H2M", 2),
    ],
)
def test_parse_duration_valid(iso_duration: str, expected_minutes: int) -> None:
    assert _parse_duration(iso_duration) == expected_minutes


@pytest.mark.parametrize(
    "invalid",
    [
        "P1DT2H",  # date part not supported (YouTube time-only)
        "PT1.5M",  # non-integer (YouTube uses integers)
        "PT-1M",
        "PT1m",  # lowercase unit
        "duration",
        "P1H",
        "T1H",
        "PT1X",
    ],
)
def test_parse_duration_invalid_raises(invalid: str) -> None:
    with pytest.raises(ValueError, match="unsupported duration format"):
        _parse_duration(invalid)


def test_parse_duration_strips_whitespace() -> None:
    assert _parse_duration("  PT1M  ") == 1


def test_parse_duration_half_minute_total_rounding() -> None:
    """90 s = 1.5 min rounds to 2 (nearest even tie at 1.5 goes to 2)."""
    assert _parse_duration("PT1M30S") == 2


def test_parse_duration_half_minute_boundary_seconds_only() -> None:
    """30 s alone is exactly 0.5 min; ``round`` uses half-to-even → 0."""
    assert _parse_duration("PT30S") == 0


def test_parse_duration_large_values() -> None:
    assert _parse_duration("PT99H59M59S") == round((99 * 3600 + 59 * 60 + 59) / 60)
