import pytest

from tests.network.conftest import REAL_YOUTUBE_API_KEY, REAL_YOUTUBE_API_URL
from tracker.common import settings
from tracker.materials import db as materials_db


pytestmark = pytest.mark.network

DUMMY_YOUTUBE_API_KEY = "test-youtube-key"


@pytest.fixture
def real_youtube_settings(monkeypatch):
    if REAL_YOUTUBE_API_KEY:
        monkeypatch.setattr(settings, "YOUTUBE_API_KEY", REAL_YOUTUBE_API_KEY)
        monkeypatch.setattr(settings, "YOUTUBE_API_URL", REAL_YOUTUBE_API_URL)

    if settings.YOUTUBE_API_KEY == DUMMY_YOUTUBE_API_KEY:
        pytest.skip(
            "the test environment pins a dummy YOUTUBE_API_KEY; run with "
            "NETWORK_YOUTUBE_API_KEY=<real key> poetry run pytest tests/network -m network",
        )


async def test_parse_habr_real_article_opt_in():
    url = "https://habr.com/ru/articles/1016056/"

    html = await materials_db.get_html(url, http_timeout=15)
    parsed = materials_db.parse_habr(html)

    assert parsed.title == "Главная проблема vibe coding — не vibe debugging"
    assert parsed.authors == "psycura"


@pytest.mark.parametrize(
    ("video_id", "expected_title", "expected_author", "expected_duration"),
    [
        (
            "Y-wNpXtU_vg",
            "Маргинал смотрит обзор Утопиана на Itpedia (Часть 1)",
            "Кирилл Кириллович",
            36,
        ),
        (
            "XUttZ838Tw0",
            "Константин Владимиров — Распределение регистров",
            "Systems Meetups",
            46,
        ),
    ],
)
async def test_parse_youtube_real_api_opt_in(
    real_youtube_settings,
    video_id,
    expected_title,
    expected_author,
    expected_duration,
):
    result = await materials_db.parse_youtube(video_id, http_timeout=10)

    assert result.title == expected_title
    assert result.authors == expected_author
    assert result.duration == expected_duration
