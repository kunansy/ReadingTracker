import aiohttp
import bs4
import pytest

from tests.unit.materials.helpers import FakeClientSessionFactory, FakeResponse, FakeSession
from tracker.common import settings
from tracker.materials import db


def _habr_page(*, title: str | None = "  Some title  ", author: str | None = "  author_name ") -> str:
    title_tag = f'<h1 class="tm-title">{title}</h1>' if title is not None else ""
    author_tag = (
        f'<a class="tm-user-info__username">{author}</a>' if author is not None else ""
    )
    return f"""
    <html><body>
      <div class="tm-article-presenter__header">{title_tag}{author_tag}</div>
    </body></html>
    """


def test_parse_habr_extracts_stripped_title_and_author():
    result = db.parse_habr(_habr_page())

    assert result == db.HabrArticle(title="Some title", authors="author_name")


def test_parse_habr_keeps_cyrillic_and_nested_markup():
    html = _habr_page(
        title="<span>Главная проблема vibe coding — не vibe debugging</span>",
        author="пользователь",
    )

    result = db.parse_habr(html)

    assert result.title == "Главная проблема vibe coding — не vibe debugging"
    assert result.authors == "пользователь"


def test_parse_habr_ignores_title_outside_the_article_header():
    html = """
    <html><body>
      <h1 class="tm-title">Outside</h1>
      <a class="tm-user-info__username">outsider</a>
    </body></html>
    """

    with pytest.raises(ValueError, match="^Title or authors not found$"):
        db.parse_habr(html)


@pytest.mark.parametrize(
    "html",
    ["", "<html></html>", "not html at all", _habr_page(title=None, author=None)],
    ids=["empty", "empty-document", "plain-text", "empty-header"],
)
def test_parse_habr_without_title_and_authors_raises(html):
    with pytest.raises(ValueError, match="^Title or authors not found$"):
        db.parse_habr(html)


@pytest.mark.xfail(
    strict=True,
    reason=(
        "BUG: tracker/materials/db.py:1010 `not (title or authors)` only fails when both "
        "are missing, so an article without a title is returned with title=''"
    ),
)
@pytest.mark.parametrize("title", [None, "", "   "], ids=["no-tag", "empty-tag", "blank-tag"])
def test_parse_habr_without_title_raises(title):
    with pytest.raises(ValueError, match="^Title or authors not found$"):
        db.parse_habr(_habr_page(title=title))


@pytest.mark.xfail(
    strict=True,
    reason=(
        "BUG: tracker/materials/db.py:1010 `not (title or authors)` only fails when both "
        "are missing, so an article without an author is returned with authors=''"
    ),
)
@pytest.mark.parametrize("author", [None, "", "   "], ids=["no-tag", "empty-tag", "blank-tag"])
def test_parse_habr_without_authors_raises(author):
    with pytest.raises(ValueError, match="^Title or authors not found$"):
        db.parse_habr(_habr_page(author=author))


def test_get_text_of_tag_is_stripped():
    soup = bs4.BeautifulSoup("<p>  текст <b>bold</b> </p>", "lxml")

    assert db._get_text(soup.find("p")) == "текстbold"


@pytest.mark.parametrize(
    "field",
    [None, bs4.NavigableString("  raw text ")],
    ids=["none", "navigable-string"],
)
def test_get_text_of_non_tag_is_empty(field):
    assert db._get_text(field) == ""


@pytest.mark.parametrize(
    ("iso_duration", "expected_minutes"),
    [
        ("", 0),
        ("   ", 0),
        ("PT", 0),
        ("PT0S", 0),
        ("PT0M", 0),
        ("PT0H0M0S", 0),
        ("PT1S", 0),
        ("PT29S", 0),
        # exactly half a minute: `round` goes to the even neighbour
        ("PT30S", 0),
        ("PT31S", 1),
        ("PT59S", 1),
        ("PT60S", 1),
        ("PT89S", 1),
        ("PT90S", 2),
        ("PT1M", 1),
        ("PT2M", 2),
        ("PT1M29S", 1),
        ("PT1M30S", 2),
        ("PT2M30S", 2),
        ("PT5M30S", 6),
        ("PT4M13S", 4),
        ("PT1H", 60),
        ("PT10H", 600),
        ("PT1H30M", 90),
        ("PT1H2M3S", 62),
        ("PT1H0M0S", 60),
        ("PT0H1M0S", 1),
        ("PT1H30S", 60),
        ("PT1H31S", 61),
        ("PT10H15M30S", 616),
        ("PT2M0S", 2),
        ("PT0H2M", 2),
        ("PT99H59M59S", 6000),
        ("PT120M", 120),
        ("  PT1M  ", 1),
        ("\tPT1H\n", 60),
    ],
)
def test_parse_duration_rounds_to_minutes(iso_duration, expected_minutes):
    assert db._parse_duration(iso_duration) == expected_minutes


@pytest.mark.parametrize(
    "invalid",
    [
        "P1DT2H",
        "PT1.5M",
        "PT-1M",
        "PT1m",
        "pt1M",
        "duration",
        "P1H",
        "T1H",
        "PT1X",
        "PT1S1M",
        "PT1M1M",
        "PT 1M",
        "1:02:03",
        "PT1H\nPT1M",
    ],
)
def test_parse_duration_rejects_unsupported_format(invalid):
    with pytest.raises(ValueError, match="^unsupported duration format: "):
        db._parse_duration(invalid)


@pytest.fixture
def http(mocker):
    def _install(response: FakeResponse) -> FakeClientSessionFactory:
        factory = FakeClientSessionFactory(FakeSession(response))
        mocker.patch.object(aiohttp, "ClientSession", factory)
        return factory

    return _install


def _response_error(status: int) -> aiohttp.ClientResponseError:
    return aiohttp.ClientResponseError(
        request_info=None,  # type: ignore[arg-type]
        history=(),
        status=status,
        message="error",
    )


async def test_get_html_returns_page_text_decoded_as_utf8(http):
    response = FakeResponse(text="<html>Привет</html>")
    factory = http(response)

    html = await db.get_html("https://habr.com/ru/articles/1/")

    assert html == "<html>Привет</html>"
    assert factory.session.get_calls == [("https://habr.com/ru/articles/1/", None)]
    assert response.calls == ["raise_for_status", "text"]
    assert response.text_encodings == ["utf-8"]
    assert factory.session.is_closed


@pytest.mark.parametrize(
    ("kwargs", "expected_total"),
    [({}, 5), ({"http_timeout": 15}, 15)],
    ids=["default", "explicit"],
)
async def test_get_html_passes_total_timeout(http, kwargs, expected_total):
    factory = http(FakeResponse(text=""))

    await db.get_html("https://habr.com/", **kwargs)

    assert [timeout.total for timeout in factory.timeouts] == [expected_total]


@pytest.mark.parametrize("status", [404, 500])
async def test_get_html_raises_on_error_status_without_reading_the_body(http, status):
    response = FakeResponse(text="error page", raise_for_status_exc=_response_error(status))
    factory = http(response)

    with pytest.raises(aiohttp.ClientResponseError) as exc_info:
        await db.get_html("https://habr.com/")

    assert exc_info.value.status == status
    assert response.calls == ["raise_for_status"]
    assert factory.session.is_closed


def _youtube_payload(duration: str = "PT1H2M3S", *, title: str = "Лекция", channel: str = "Канал"):
    return {
        "items": [
            {
                "snippet": {"title": title, "channelTitle": channel},
                "contentDetails": {"duration": duration},
            },
            {
                "snippet": {"title": "second", "channelTitle": "ignored"},
                "contentDetails": {"duration": "PT9H"},
            },
        ],
    }


@pytest.mark.parametrize(
    ("video_id", "duration", "expected_minutes"),
    [
        ("Y-wNpXtU_vg", "PT1H2M3S", 62),
        ("XUttZ838Tw0", "PT2M", 2),
        ("XUttZ838Tw0", "PT59S", 1),
        ("Y-wNpXtU_vg", "PT0S", 0),
        ("Y-wNpXtU_vg", "PT1H", 60),
        ("Y-wNpXtU_vg", "PT1H30M", 90),
        ("Y-wNpXtU_vg", "PT1M30S", 2),
        ("Y-wNpXtU_vg", "", 0),
    ],
)
async def test_parse_youtube_returns_the_first_video(http, video_id, duration, expected_minutes):
    factory = http(FakeResponse(json_data=_youtube_payload(duration)))

    result = await db.parse_youtube(video_id)

    assert result == db.YoutubeVideo(title="Лекция", authors="Канал", duration=expected_minutes)
    assert factory.session.is_closed


async def test_parse_youtube_requests_the_api_with_the_configured_key(mocker, http):
    mocker.patch.object(settings, "YOUTUBE_API_URL", "https://example.test/youtube")
    mocker.patch.object(settings, "YOUTUBE_API_KEY", "secret-key")
    factory = http(FakeResponse(json_data=_youtube_payload()))

    await db.parse_youtube("Y-wNpXtU_vg")

    assert factory.session.get_calls == [
        (
            "https://example.test/youtube",
            {"part": "snippet,contentDetails", "id": "Y-wNpXtU_vg", "key": "secret-key"},
        ),
    ]


async def test_parse_youtube_uses_pinned_test_settings_by_default(http):
    factory = http(FakeResponse(json_data=_youtube_payload()))

    await db.parse_youtube("id")

    [(url, params)] = factory.session.get_calls
    assert url == "https://youtube.test/v3/videos"
    assert params["key"] == "test-youtube-key"


@pytest.mark.parametrize(
    ("kwargs", "expected_total"),
    [({}, 5), ({"http_timeout": 10}, 10)],
    ids=["default", "explicit"],
)
async def test_parse_youtube_passes_total_timeout(http, kwargs, expected_total):
    factory = http(FakeResponse(json_data=_youtube_payload()))

    await db.parse_youtube("id", **kwargs)

    assert [timeout.total for timeout in factory.timeouts] == [expected_total]


async def test_parse_youtube_of_unknown_video_raises_value_error(http):
    http(FakeResponse(json_data={"items": []}))

    with pytest.raises(ValueError, match="^No items found$"):
        await db.parse_youtube("unknown")


async def test_parse_youtube_rejects_unsupported_duration(http):
    http(FakeResponse(json_data=_youtube_payload("P1DT2H")))

    with pytest.raises(ValueError, match="unsupported duration format"):
        await db.parse_youtube("id")


@pytest.mark.parametrize(
    ("payload", "missing_key"),
    [
        ({}, "items"),
        ({"items": [{}]}, "snippet"),
        ({"items": [{"snippet": {}}]}, "title"),
        ({"items": [{"snippet": {"title": "t"}}]}, "channelTitle"),
        ({"items": [{"snippet": {"title": "t", "channelTitle": "c"}}]}, "contentDetails"),
        ({"items": [{"contentDetails": {"duration": "PT2M"}}]}, "snippet"),
        (
            {"items": [{"snippet": {"title": "t", "channelTitle": "c"}, "contentDetails": {}}]},
            "duration",
        ),
    ],
    ids=[
        "no-items",
        "empty-item",
        "empty-snippet",
        "no-channel",
        "no-content-details",
        "no-snippet",
        "no-duration",
    ],
)
async def test_parse_youtube_of_incomplete_payload_raises_key_error_current_behaviour(
    http,
    payload,
    missing_key,
):
    http(FakeResponse(json_data=payload))

    with pytest.raises(KeyError, match=missing_key):
        await db.parse_youtube("id")


@pytest.mark.parametrize("status", [400, 403, 500])
async def test_parse_youtube_error_status_raises_aiohttp_error_current_behaviour(http, status):
    response = FakeResponse(
        json_data={"error": {"code": status}},
        raise_for_status_exc=_response_error(status),
    )
    factory = http(response)

    with pytest.raises(aiohttp.ClientResponseError) as exc_info:
        await db.parse_youtube("Y-wNpXtU_vg")

    assert exc_info.value.status == status
    assert not isinstance(exc_info.value, ValueError)
    assert factory.session.is_closed


async def test_parse_youtube_reads_the_body_before_checking_the_status_current_behaviour(http):
    response = FakeResponse(
        json_data={"error": {"code": 403}},
        raise_for_status_exc=_response_error(403),
    )
    http(response)

    with pytest.raises(aiohttp.ClientResponseError):
        await db.parse_youtube("Y-wNpXtU_vg")

    assert response.calls == ["json", "raise_for_status"]
