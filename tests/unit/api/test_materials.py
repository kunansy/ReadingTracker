import datetime
import logging
from decimal import Decimal
from types import SimpleNamespace

import aiohttp
import pytest
from fastapi import HTTPException

from tests.unit.api import factories
from tracker.api.v1 import materials as materials_api
from tracker.common import database, pagination
from tracker.materials import db as materials_db, schemas
from tracker.models import enums
from tracker.reading_log import db as reading_log_db


BASE = "/api/v1/materials"
MATERIAL_URL = f"{BASE}/{factories.MATERIAL_ID}"
NOT_FOUND = database.NotFoundException("Material not found")
NOT_FOUND_BODY = {"detail": "NotFoundError: Material not found"}


def _patch(mocker, name: str, **kwargs):
    return mocker.patch.object(materials_db, name, mocker.AsyncMock(**kwargs))


@pytest.fixture
def estimate_page(mocker):
    return _patch(mocker, "estimate_page", return_value=factories.page())


@pytest.fixture
def get_means(mocker):
    return _patch(mocker, "get_means", return_value={})


@pytest.fixture
def today(dependency_overrides):
    dependency_overrides[database.utc_today] = lambda: factories.TODAY
    return factories.TODAY


async def test_queue_defaults_start_date_to_today(
    client, estimate_page, get_means, today
):
    response = await client.get(f"{BASE}/queue")

    assert response.status_code == 200
    assert response.json() == {
        "estimates": [],
        "mean": {},
        "next_token": None,
        "total_count": 0,
    }
    estimate_page.assert_awaited_once_with(
        start_date=today, params=pagination.PageParams()
    )
    get_means.assert_awaited_once_with()


async def test_queue_uses_the_requested_start_date(
    client, estimate_page, get_means, today
):
    response = await client.get(
        f"{BASE}/queue", params={"start_date": "2026-12-31", "page_size": 3}
    )

    assert response.status_code == 200
    estimate_page.assert_awaited_once_with(
        start_date=datetime.date(2026, 12, 31),
        params=pagination.PageParams(page_size=3),
    )


async def test_queue_serializes_estimates_and_means(
    client, estimate_page, get_means, today
):
    estimate = materials_db.MaterialEstimate(
        material=factories.material(link="https://example.com/book"),
        will_be_started=datetime.date(2026, 3, 10),
        will_be_completed=datetime.date(2026, 4, 1),
        expected_duration=22,
    )
    estimate_page.return_value = pagination.Page(
        items=[estimate], next_token="next", total_count=9
    )
    get_means.return_value = {
        enums.MaterialTypesEnum.book: Decimal("1.50"),
        enums.MaterialTypesEnum.article: Decimal(0),
    }

    response = await client.get(f"{BASE}/queue")

    assert response.status_code == 200
    assert response.json() == {
        "estimates": [
            {
                "material": factories.material_json(link="https://example.com/book"),
                "will_be_started": "2026-03-10",
                "will_be_completed": "2026-04-01",
                "expected_duration": 22,
            },
        ],
        "mean": {"book": 1.5, "article": 0.0},
        "next_token": "next",
        "total_count": 9,
    }


@pytest.mark.parametrize(
    "params",
    [
        {"page_size": 0},
        {"page_size": 101},
        {"next_token": "a" * (pagination.MAX_TOKEN_LENGTH + 1)},
        {"start_date": "tomorrow"},
    ],
    ids=["page-size-zero", "page-size-over-max", "token-too-long", "bad-date"],
)
async def test_queue_rejects_invalid_query(
    client, estimate_page, get_means, today, params
):
    response = await client.get(f"{BASE}/queue", params=params)

    assert response.status_code == 422
    estimate_page.assert_not_awaited()


@pytest.mark.xfail(
    strict=True,
    reason=(
        "BUG: tracker/api/v1/materials.py:25 an error raised inside asyncio.TaskGroup "
        "reaches the app as ExceptionGroup, so a malformed next_token is 500 instead of 422"
    ),
)
async def test_queue_maps_invalid_token_to_422(
    lenient_client, estimate_page, get_means, today
):
    estimate_page.side_effect = database.InvalidNextTokenException(
        "next_token is malformed"
    )

    response = await lenient_client.get(f"{BASE}/queue", params={"next_token": "garbage"})

    assert response.status_code == 422
    assert response.json() == {"detail": "InvalidNextToken: next_token is malformed"}


@pytest.mark.parametrize(
    ("path", "db_function", "response_key"),
    [
        ("reading", "reading_statistics_page", "statistics"),
        ("completed", "completed_statistics_page", "statistics"),
    ],
)
async def test_statistics_listing_serializes_the_page(
    client, mocker, path, db_function, response_key
):
    completed = factories.material_statistics(
        material=factories.material(pages=0),
        min_record=database.MinMax(
            log_id=factories.LOG_ID,
            material_id=factories.MATERIAL_ID,
            count=1,
            date=datetime.date(2026, 1, 11),
        ),
        remaining_pages=0,
        remaining_days=0,
        completed_at=datetime.date(2026, 1, 30),
        total_reading_duration="20 days",
        would_be_completed=datetime.date(2026, 2, 1),
    )
    _patch(
        mocker,
        db_function,
        return_value=pagination.Page(
            items=[factories.material_statistics(), completed],
            next_token="next",
            total_count=2,
        ),
    )

    response = await client.get(f"{BASE}/{path}")

    assert response.status_code == 200
    assert response.json() == {
        response_key: [
            factories.material_statistics_json(),
            factories.material_statistics_json(
                material=factories.material_json(pages=0),
                min_record={
                    "log_id": str(factories.LOG_ID),
                    "material_id": str(factories.MATERIAL_ID),
                    "material_title": "",
                    "count": 1,
                    "date": "2026-01-11",
                },
                remaining_pages=0,
                remaining_days=0,
                completed_at="2026-01-30",
                total_reading_duration="20 days",
                would_be_completed="2026-02-01",
                percent_completed=0.0,
            ),
        ],
        "next_token": "next",
        "total_count": 2,
    }


async def test_reading_passes_page_params(client, mocker):
    get_page = _patch(mocker, "reading_statistics_page", return_value=factories.page())

    response = await client.get(
        f"{BASE}/reading", params={"page_size": 1, "order": "desc"}
    )

    assert response.status_code == 200
    assert response.json() == {"statistics": [], "next_token": None, "total_count": 0}
    get_page.assert_awaited_once_with(
        params=pagination.PageParams(page_size=1, order=pagination.Order.DESC)
    )


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({}, {"material_type": None, "is_outlined": None, "tags": set()}),
        (
            {"material_type": "book", "is_outlined": "true", "tags_query": "a b"},
            {
                "material_type": enums.MaterialTypesEnum.book,
                "is_outlined": True,
                "tags": {"a", "b"},
            },
        ),
        (
            {"material_type": "", "is_outlined": "false", "tags_query": "  "},
            {"material_type": None, "is_outlined": False, "tags": set()},
        ),
        (
            {"tags_query": " тег  tag\tтег "},
            {"material_type": None, "is_outlined": None, "tags": {"тег", "tag"}},
        ),
    ],
    ids=["no-filters", "all-filters", "empty-form-values", "duplicate-cyrillic-tags"],
)
async def test_completed_passes_filters(client, mocker, params, expected):
    get_page = _patch(mocker, "completed_statistics_page", return_value=factories.page())

    response = await client.get(f"{BASE}/completed", params=params)

    assert response.status_code == 200
    get_page.assert_awaited_once_with(**expected, params=pagination.PageParams())


@pytest.mark.parametrize(
    "params",
    [{"is_outlined": "maybe"}, {"material_type": "podcast"}, {"page_size": 0}],
    ids=["bad-bool", "unknown-type", "page-size-zero"],
)
async def test_completed_rejects_invalid_query(client, mocker, params):
    get_page = _patch(mocker, "completed_statistics_page", return_value=factories.page())

    response = await client.get(f"{BASE}/completed", params=params)

    assert response.status_code == 422
    get_page.assert_not_awaited()


@pytest.mark.parametrize(
    ("path", "db_function"),
    [
        ("reading", "reading_statistics_page"),
        ("completed", "completed_statistics_page"),
        ("repeat", "get_repeating_queue_page"),
    ],
)
async def test_listing_maps_invalid_token_to_422(client, mocker, path, db_function):
    _patch(
        mocker,
        db_function,
        side_effect=database.InvalidNextTokenException("next_token is malformed"),
    )

    response = await client.get(f"{BASE}/{path}", params={"next_token": "garbage"})

    assert response.status_code == 422
    assert response.json() == {"detail": "InvalidNextToken: next_token is malformed"}


async def test_get_completed_material(client, mocker):
    get_statistics = _patch(
        mocker, "get_completed_statistics", return_value=factories.material_statistics()
    )

    response = await client.get(f"{BASE}/completed/{factories.MATERIAL_ID}")

    assert response.status_code == 200
    assert response.json() == {"statistics": factories.material_statistics_json()}
    get_statistics.assert_awaited_once_with(material_id=factories.MATERIAL_ID)


async def test_get_completed_material_that_is_missing_is_404(client, mocker):
    _patch(mocker, "get_completed_statistics", side_effect=NOT_FOUND)

    response = await client.get(f"{BASE}/completed/{factories.MATERIAL_ID}")

    assert response.status_code == 404
    assert response.json() == NOT_FOUND_BODY


async def test_get_completed_material_rejects_bad_uuid(client):
    response = await client.get(f"{BASE}/completed/42")

    assert response.status_code == 422
    assert response.json()["detail"].startswith("path.material_id: ")


@pytest.mark.parametrize(
    ("params", "is_outlined"),
    [({}, False), ({"only_outlined": "true"}, True), ({"only_outlined": "0"}, False)],
    ids=["default", "true", "zero"],
)
async def test_repeat_passes_the_outlined_filter(client, mocker, params, is_outlined):
    get_page = _patch(mocker, "get_repeating_queue_page", return_value=factories.page())

    response = await client.get(f"{BASE}/repeat", params=params)

    assert response.status_code == 200
    assert response.json() == {
        "repeating_queue": [],
        "next_token": None,
        "total_count": 0,
    }
    get_page.assert_awaited_once_with(
        is_outlined=is_outlined, params=pagination.PageParams()
    )


async def test_repeat_serializes_the_page(client, mocker):
    item = materials_db.RepeatingQueue(
        material_id=factories.MATERIAL_ID,
        title="Война и мир",
        pages=1300,
        material_type=enums.MaterialTypesEnum.book,
        is_outlined=True,
        notes_count=4,
        cards_count=0,
        repeats_count=2,
        completed_at=datetime.datetime(2026, 1, 30, 10, 0),
        last_repeated_at=None,
        priority_days=-3,
        priority_months=1.5,
    )
    _patch(
        mocker,
        "get_repeating_queue_page",
        return_value=pagination.Page(items=[item], next_token=None, total_count=1),
    )

    response = await client.get(f"{BASE}/repeat")

    assert response.status_code == 200
    assert response.json() == {
        "repeating_queue": [
            {
                "material_id": str(factories.MATERIAL_ID),
                "title": "Война и мир",
                "pages": 1300,
                "material_type": "book",
                "is_outlined": True,
                "notes_count": 4,
                "cards_count": 0,
                "repeats_count": 2,
                "completed_at": "2026-01-30T10:00:00",
                "last_repeated_at": None,
                "priority_days": -3,
                "priority_months": 1.5,
            },
        ],
        "next_token": None,
        "total_count": 1,
    }


async def test_repeat_rejects_bad_bool(client, mocker):
    get_page = _patch(mocker, "get_repeating_queue_page", return_value=factories.page())

    response = await client.get(f"{BASE}/repeat", params={"only_outlined": "maybe"})

    assert response.status_code == 422
    get_page.assert_not_awaited()


@pytest.mark.parametrize(
    ("authors", "expected"),
    [((), []), (("Лев Толстой", "Knuth"), ["Лев Толстой", "Knuth"])],
    ids=["empty", "some"],
)
async def test_get_authors(client, mocker, authors, expected):
    get_authors = _patch(mocker, "get_authors", return_value=authors)

    response = await client.get(f"{BASE}/authors")

    assert response.status_code == 200
    assert response.json() == {"authors": expected}
    get_authors.assert_awaited_once_with()


@pytest.mark.parametrize(
    ("tags", "expected"),
    [(set(), []), ({"b", "a", "тег"}, ["a", "b", "тег"])],
    ids=["empty", "some"],
)
async def test_get_tags(client, mocker, tags, expected):
    _patch(mocker, "get_material_tags", return_value=tags)

    response = await client.get(f"{BASE}/tags")

    assert response.status_code == 200
    assert sorted(response.json()["tags"]) == expected


@pytest.mark.parametrize(
    ("path", "db_function"),
    [
        ("titles", "get_titles"),
        ("read-titles", "get_read_material_titles"),
        ("reading-titles", "get_reading_material_titles"),
        ("with-cards-titles", "list_material_titles_with_cards"),
    ],
)
@pytest.mark.parametrize(
    ("titles", "expected"),
    [
        ({}, {}),
        (
            {factories.MATERIAL_ID: "Война и мир", factories.OTHER_MATERIAL_ID: ""},
            {
                str(factories.MATERIAL_ID): "Война и мир",
                str(factories.OTHER_MATERIAL_ID): "",
            },
        ),
    ],
    ids=["empty", "some"],
)
async def test_titles_listing(client, mocker, path, db_function, titles, expected):
    get_titles = _patch(mocker, db_function, return_value=titles)

    response = await client.get(f"{BASE}/{path}")

    assert response.status_code == 200
    assert response.json() == {"items": expected}
    get_titles.assert_awaited_once_with()


@pytest.mark.parametrize("is_reading", [True, False])
async def test_is_reading(client, mocker, is_reading):
    check = _patch(mocker, "is_reading", return_value=is_reading)

    response = await client.get(
        f"{BASE}/is-reading", params={"material_id": str(factories.MATERIAL_ID)}
    )

    assert response.status_code == 200
    assert response.json() == {"is_reading": is_reading}
    check.assert_awaited_once_with(material_id=factories.MATERIAL_ID)


@pytest.mark.parametrize(
    "params", [{}, {"material_id": "x"}], ids=["missing", "bad-uuid"]
)
async def test_is_reading_requires_a_valid_material_id(client, mocker, params):
    check = _patch(mocker, "is_reading", return_value=True)

    response = await client.get(f"{BASE}/is-reading", params=params)

    assert response.status_code == 422
    assert response.json()["detail"].startswith("query.material_id: ")
    check.assert_not_awaited()


@pytest.fixture
def habr(mocker):
    return SimpleNamespace(
        get_html=_patch(mocker, "get_html", return_value="<html>habr</html>"),
        parse=mocker.patch.object(
            materials_db,
            "parse_habr",
            mocker.Mock(
                return_value=materials_db.HabrArticle(title="Статья", authors="author")
            ),
        ),
    )


@pytest.mark.parametrize(
    "link",
    ["https://habr.com/ru/articles/1/", "http://habr.ru/post/1"],
    ids=["com", "ru"],
)
async def test_parse_habr(client, habr, link):
    response = await client.post(f"{BASE}/parse/habr", json={"link": link})

    assert response.status_code == 200
    assert response.json() == {
        "authors": "author",
        "title": "Статья",
        "type": "article",
        "link": link,
        "duration": None,
    }
    habr.get_html.assert_awaited_once_with(link)
    habr.parse.assert_called_once_with("<html>habr</html>")


@pytest.mark.parametrize(
    "link",
    [
        "https://example.com/post",
        "https://habr.org/post",
        "https://nothabr.com/post",
        "https://habrahabr.ru/post",
        "https://127.0.0.1/habr.com",
        "https://evil.com/?u=habr.com",
    ],
    ids=["other-site", "other-tld", "suffix-match", "old-domain", "ip", "habr-in-query"],
)
async def test_parse_habr_rejects_a_foreign_host(client, habr, link):
    response = await client.post(f"{BASE}/parse/habr", json={"link": link})

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid habr url"}
    habr.get_html.assert_not_awaited()


@pytest.mark.xfail(
    strict=True,
    reason=(
        "BUG: tracker/api/v1/materials.py:177 the host check is startswith('habr.') + "
        "endswith('.com'), so habr.evil.com passes and the server fetches a foreign page"
    ),
)
async def test_parse_habr_rejects_a_lookalike_host(client, habr):
    response = await client.post(
        f"{BASE}/parse/habr", json={"link": "https://habr.evil.com/post"}
    )

    assert response.status_code == 400
    habr.get_html.assert_not_awaited()


async def test_parse_habr_rejects_the_www_host_current_behaviour(client, habr):
    response = await client.post(
        f"{BASE}/parse/habr", json={"link": "https://www.habr.com/ru/articles/1/"}
    )

    assert response.status_code == 400


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"link": "not a url"},
        {"link": "ftp://habr.com/x"},
        {"link": "https://habr.com", "x": 1},
    ],
    ids=["missing", "not-url", "ftp-scheme", "extra-field"],
)
@pytest.mark.parametrize("site", ["habr", "youtube"])
async def test_parse_rejects_invalid_body(client, site, body):
    response = await client.post(f"{BASE}/parse/{site}", json=body)

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("endpoint", "detail"),
    [
        (materials_api.parse_habr, "Invalid habr url"),
        (materials_api.parse_youtube, "Invalid YouTube url"),
    ],
)
async def test_parse_rejects_a_link_without_host(endpoint, detail):
    # HttpUrl always has a host, so the guard is reachable only by a direct call
    payload = SimpleNamespace(link=SimpleNamespace(host=None))

    with pytest.raises(HTTPException) as e:
        await endpoint(payload)

    assert e.value.status_code == 400
    assert e.value.detail == detail


@pytest.mark.xfail(
    strict=True,
    reason=(
        "BUG: tracker/api/v1/materials.py:181 ValueError of db.parse_habr (a page that "
        "is not a habr article) is not caught, giving 500 instead of 400 as parse/youtube does"
    ),
)
async def test_parse_habr_maps_an_unparsable_page_to_400(lenient_client, habr):
    habr.parse.side_effect = ValueError("Title or authors not found")

    response = await lenient_client.post(
        f"{BASE}/parse/habr", json={"link": "https://habr.com/ru/articles/1/"}
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Title or authors not found"}


async def test_parse_habr_download_failure_is_500_current_behaviour(lenient_client, habr):
    habr.get_html.side_effect = aiohttp.ClientConnectionError("unreachable")

    response = await lenient_client.post(
        f"{BASE}/parse/habr", json={"link": "https://habr.com/ru/articles/1/"}
    )

    assert response.status_code == 500
    habr.parse.assert_not_called()


@pytest.fixture
def youtube(mocker):
    return _patch(
        mocker,
        "parse_youtube",
        return_value=materials_db.YoutubeVideo(
            title="Лекция", authors="Channel", duration=0
        ),
    )


@pytest.mark.parametrize(
    ("link", "video_id"),
    [
        ("https://youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ?t=10", "dQw4w9WgXcQ"),
        ("https://www.youtu.be/dQw4w9WgXcQ/", "dQw4w9WgXcQ"),
        ("http://youtube.com/watch?v=a-b_c", "a-b_c"),
    ],
    ids=[
        "watch",
        "www-watch-extra-param",
        "short",
        "short-with-query",
        "www-short",
        "http",
    ],
)
async def test_parse_youtube(client, youtube, link, video_id):
    response = await client.post(f"{BASE}/parse/youtube", json={"link": link})

    assert response.status_code == 200
    assert response.json() == {
        "authors": "Channel",
        "title": "Лекция",
        "type": "lecture",
        "link": f"https://youtube.com/watch?v={video_id}",
        "duration": 0,
    }
    youtube.assert_awaited_once_with(video_id)


@pytest.mark.parametrize(
    "link",
    [
        "https://example.com/watch?v=X",
        "https://youtube.ru/watch?v=X",
        "https://notyoutube.com/watch?v=X",
        "https://youtube.com.evil.com/watch?v=X",
        "https://vimeo.com/youtu.be",
    ],
    ids=["other-site", "other-tld", "suffix-match", "prefix-match", "youtube-in-path"],
)
async def test_parse_youtube_rejects_a_foreign_host(client, youtube, link):
    response = await client.post(f"{BASE}/parse/youtube", json={"link": link})

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid YouTube url"}
    youtube.assert_not_awaited()


@pytest.mark.xfail(
    strict=True,
    reason=(
        "BUG: tracker/api/v1/materials.py:198 host.replace('www.', '') removes 'www.' "
        "anywhere in the host, so youwww.tube.com is accepted as youtube.com"
    ),
)
async def test_parse_youtube_rejects_a_host_with_www_inside(client, youtube):
    response = await client.post(
        f"{BASE}/parse/youtube", json={"link": "https://youwww.tube.com/watch?v=X"}
    )

    assert response.status_code == 400
    youtube.assert_not_awaited()


async def test_parse_youtube_rejects_the_mobile_host_current_behaviour(client, youtube):
    response = await client.post(
        f"{BASE}/parse/youtube", json={"link": "https://m.youtube.com/watch?v=X"}
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid YouTube url"}


@pytest.mark.xfail(
    strict=True,
    reason=(
        "BUG: tracker/api/v1/materials.py:202 link.query_params()[0][1] takes the first "
        "query parameter instead of 'v', so watch?t=10&v=X looks up video '10'"
    ),
)
@pytest.mark.parametrize(
    "link",
    [
        "https://www.youtube.com/watch?t=10&v=dQw4w9WgXcQ",
        "https://youtube.com/watch?list=PL1&v=dQw4w9WgXcQ",
    ],
    ids=["time-first", "playlist-first"],
)
async def test_parse_youtube_takes_the_v_parameter(client, youtube, link):
    response = await client.post(f"{BASE}/parse/youtube", json={"link": link})

    assert response.status_code == 200
    youtube.assert_awaited_once_with("dQw4w9WgXcQ")
    assert response.json()["link"] == "https://youtube.com/watch?v=dQw4w9WgXcQ"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "BUG: tracker/api/v1/materials.py:202 link.query_params()[0] raises IndexError "
        "for a youtube.com link without a query string, giving 500 instead of 400"
    ),
)
@pytest.mark.parametrize(
    "link",
    [
        "https://youtube.com/shorts/dQw4w9WgXcQ",
        "https://www.youtube.com/",
        "https://youtube.com/watch",
    ],
    ids=["shorts", "root", "watch-without-query"],
)
async def test_parse_youtube_link_without_query_is_a_client_error(
    lenient_client, youtube, link
):
    response = await lenient_client.post(f"{BASE}/parse/youtube", json={"link": link})

    assert response.status_code == 400


async def test_parse_youtube_short_link_without_id_looks_up_an_empty_id_current_behaviour(
    client, youtube
):
    response = await client.post(
        f"{BASE}/parse/youtube", json={"link": "https://youtu.be"}
    )

    assert response.status_code == 200
    youtube.assert_awaited_once_with("")


async def test_parse_youtube_maps_an_unknown_video_to_400(client, youtube, tracker_log):
    youtube.side_effect = ValueError("No items found")

    response = await client.post(
        f"{BASE}/parse/youtube", json={"link": "https://youtu.be/missing"}
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "No items found"}
    errors = tracker_log(logging.ERROR)
    assert len(errors) == 1
    assert errors[0].getMessage() == (
        "Failed to parse YouTube, link=https://youtu.be/missing, "
        "e=ValueError('No items found')"
    )


async def test_parse_youtube_api_failure_is_500_current_behaviour(
    lenient_client, youtube
):
    youtube.side_effect = aiohttp.ClientConnectionError("unreachable")

    response = await lenient_client.post(
        f"{BASE}/parse/youtube", json={"link": "https://youtu.be/X"}
    )

    assert response.status_code == 500


def _material_body(**patch) -> dict:
    return {
        "title": "Война и мир",
        "authors": "Лев Толстой",
        "pages": 1300,
        "material_type": "book",
        **patch,
    }


@pytest.fixture
def insert_material(mocker):
    return _patch(mocker, "insert_material", return_value=factories.MATERIAL_ID)


async def test_create_material_with_required_fields_only(client, insert_material):
    response = await client.post(f"{BASE}/", json=_material_body())

    assert response.status_code == 201
    assert response.json() == {"material_id": str(factories.MATERIAL_ID)}
    insert_material.assert_awaited_once_with(
        title="Война и мир",
        authors="Лев Толстой",
        pages=1300,
        material_type=enums.MaterialTypesEnum.book,
        tags=None,
        link=None,
    )


async def test_create_material_with_every_field(client, insert_material):
    response = await client.post(
        f"{BASE}/",
        json=_material_body(
            title="  Padded  ",
            pages=1,
            material_type="audiobook",
            tags="a, b",
            link="https://example.com/book?x=1",
        ),
    )

    assert response.status_code == 201
    insert_material.assert_awaited_once_with(
        title="Padded",
        authors="Лев Толстой",
        pages=1,
        material_type=enums.MaterialTypesEnum.audiobook,
        tags="a, b",
        link="https://example.com/book?x=1",
    )


@pytest.mark.parametrize(
    ("patch", "detail"),
    [
        ({"pages": 0}, "body.pages: Input should be greater than 0"),
        ({"pages": -1}, "body.pages: Input should be greater than 0"),
        ({"material_type": "podcast"}, "body.material_type: Input should be"),
        ({"link": "not a url"}, "body.link: Input should be a valid URL"),
        ({"link": ""}, "body.link: Input should be a valid URL"),
        ({"material_id": str(factories.MATERIAL_ID)}, "body.material_id: Extra inputs"),
        ({"title": None}, "body.title: Input should be a valid string"),
    ],
    ids=[
        "zero-pages",
        "negative-pages",
        "unknown-type",
        "bad-link",
        "empty-link",
        "extra",
        "null-title",
    ],
)
async def test_create_material_rejects_invalid_body(
    client, insert_material, patch, detail
):
    response = await client.post(f"{BASE}/", json=_material_body(**patch))

    assert response.status_code == 422
    assert response.json()["detail"].startswith(detail)
    insert_material.assert_not_awaited()


async def test_create_material_maps_a_duplicate_to_409(client, insert_material):
    insert_material.side_effect = database.AlreadyExistsException("Material exists")

    response = await client.post(f"{BASE}/", json=_material_body())

    assert response.status_code == 409
    assert response.json() == {"detail": "AlreadyExistsError: Material exists"}


@pytest.fixture
def get_material_api(mocker):
    return _patch(mocker, "get_material_api", return_value=factories.material())


async def test_get_material(client, get_material_api):
    get_material_api.return_value = factories.material(
        link="https://example.com/book",
        started_at=datetime.datetime(2026, 1, 10),
        completed_at=datetime.datetime(2026, 1, 30),
    )

    response = await client.get(MATERIAL_URL)

    assert response.status_code == 200
    assert response.json() == {
        "material": factories.material_json(link="https://example.com/book"),
    }
    get_material_api.assert_awaited_once_with(material_id=factories.MATERIAL_ID)


async def test_get_material_that_is_missing_is_404(client, get_material_api):
    get_material_api.side_effect = NOT_FOUND

    response = await client.get(MATERIAL_URL)

    assert response.status_code == 404
    assert response.json() == NOT_FOUND_BODY


async def test_get_material_rejects_bad_uuid(client, get_material_api):
    response = await client.get(f"{BASE}/not-a-uuid")

    assert response.status_code == 422
    get_material_api.assert_not_awaited()


@pytest.fixture
def update_material(mocker):
    return _patch(mocker, "update_material", return_value=None)


async def test_update_material(client, update_material):
    response = await client.patch(
        MATERIAL_URL,
        json=_material_body(
            material_id=str(factories.MATERIAL_ID),
            tags="a",
            link="https://example.com/book",
        ),
    )

    assert response.status_code == 204
    assert response.content == b""
    update_material.assert_awaited_once_with(
        material_id=factories.MATERIAL_ID,
        title="Война и мир",
        authors="Лев Толстой",
        pages=1300,
        material_type=enums.MaterialTypesEnum.book,
        tags="a",
        link="https://example.com/book",
    )


async def test_update_material_clears_optional_fields_when_omitted(
    client, update_material
):
    response = await client.patch(
        MATERIAL_URL, json=_material_body(material_id=str(factories.MATERIAL_ID))
    )

    assert response.status_code == 204
    kwargs = update_material.await_args.kwargs
    assert kwargs["tags"] is None
    assert kwargs["link"] is None


async def test_update_material_rejects_a_body_for_another_material(
    client, update_material
):
    response = await client.patch(
        MATERIAL_URL, json=_material_body(material_id=str(factories.OTHER_MATERIAL_ID))
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "material_id mismatch"}
    update_material.assert_not_awaited()


@pytest.mark.parametrize(
    "body",
    [
        _material_body(),
        _material_body(material_id=str(factories.MATERIAL_ID), pages=0),
        _material_body(material_id=str(factories.MATERIAL_ID), extra=1),
    ],
    ids=["no-material-id", "zero-pages", "extra"],
)
async def test_update_material_rejects_invalid_body(client, update_material, body):
    response = await client.patch(MATERIAL_URL, json=body)

    assert response.status_code == 422
    update_material.assert_not_awaited()


async def test_update_material_that_is_missing_is_404(client, update_material):
    update_material.side_effect = NOT_FOUND

    response = await client.patch(
        MATERIAL_URL, json=_material_body(material_id=str(factories.MATERIAL_ID))
    )

    assert response.status_code == 404
    assert response.json() == NOT_FOUND_BODY


@pytest.fixture
def start(mocker, get_material_api):
    mocker.patch.object(database, "utc_today", return_value=factories.TODAY)
    return _patch(mocker, "start_material", return_value=None)


@pytest.mark.parametrize(
    ("body", "started_at"),
    [
        ({}, None),
        ({"started_at": None}, None),
        ({"started_at": "2026-03-10"}, factories.TODAY),
        ({"started_at": "2026-03-09"}, datetime.date(2026, 3, 9)),
        ({"started_at": "1970-01-01"}, datetime.date(1970, 1, 1)),
    ],
    ids=["omitted", "null", "today", "yesterday", "long-ago"],
)
async def test_start_material(client, start, get_material_api, body, started_at):
    response = await client.post(f"{MATERIAL_URL}/start", json=body)

    assert response.status_code == 204
    get_material_api.assert_awaited_once_with(material_id=factories.MATERIAL_ID)
    start.assert_awaited_once_with(
        material_id=factories.MATERIAL_ID, started_at=started_at
    )


@pytest.mark.parametrize(
    "started_at", ["2026-03-11", "2100-01-01"], ids=["tomorrow", "far"]
)
async def test_start_material_rejects_a_future_date(client, start, started_at):
    response = await client.post(f"{MATERIAL_URL}/start", json={"started_at": started_at})

    assert response.status_code == 400
    assert response.json() == {"detail": "Start date must not be in the future"}
    start.assert_not_awaited()


@pytest.mark.parametrize(
    "body", [{}, {"started_at": "2100-01-01"}], ids=["no-date", "future"]
)
async def test_start_material_rejects_a_started_material(
    client, start, get_material_api, body
):
    get_material_api.return_value = factories.material(
        started_at=datetime.datetime(2026, 1, 10)
    )

    response = await client.post(f"{MATERIAL_URL}/start", json=body)

    assert response.status_code == 400
    assert response.json() == {"detail": "Material is already started"}
    start.assert_not_awaited()


async def test_start_material_that_is_missing_is_404(client, start, get_material_api):
    get_material_api.side_effect = NOT_FOUND

    response = await client.post(f"{MATERIAL_URL}/start", json={})

    assert response.status_code == 404
    assert response.json() == NOT_FOUND_BODY
    start.assert_not_awaited()


async def test_start_material_maps_a_lost_race_to_409(client, start):
    start.side_effect = database.ConflictException("Material is not in the queue")

    response = await client.post(f"{MATERIAL_URL}/start", json={})

    assert response.status_code == 409
    assert response.json() == {"detail": "ConflictError: Material is not in the queue"}


@pytest.mark.parametrize(
    "request_kwargs",
    [{}, {"json": {"started_at": "soon"}}, {"json": {"started_at": None, "x": 1}}],
    ids=["no-body", "bad-date", "extra"],
)
async def test_start_material_rejects_invalid_body(client, start, request_kwargs):
    response = await client.post(f"{MATERIAL_URL}/start", **request_kwargs)

    assert response.status_code == 422
    start.assert_not_awaited()


@pytest.fixture
def complete(mocker):
    return SimpleNamespace(
        check=_patch(mocker, "is_completion_request_valid", return_value=None),
        complete=_patch(mocker, "complete_material", return_value=None),
    )


@pytest.mark.parametrize(
    ("body", "completed_at"),
    [({}, None), ({"completed_at": "2026-03-10"}, factories.TODAY)],
    ids=["omitted", "explicit"],
)
async def test_complete_material_checks_then_completes(
    client, complete, body, completed_at
):
    response = await client.post(f"{MATERIAL_URL}/complete", json=body)

    assert response.status_code == 204
    expected = {"material_id": factories.MATERIAL_ID, "completed_at": completed_at}
    complete.check.assert_awaited_once_with(**expected)
    complete.complete.assert_awaited_once_with(**expected)


@pytest.mark.parametrize(
    "detail",
    [
        "Completion date must not be before the start date",
        "Completion date must not be in the future",
        "Reading logs not found",
        "Invalid pages count, something is unread",
        "",
    ],
)
async def test_complete_material_maps_an_invalid_request_to_400(client, complete, detail):
    complete.check.side_effect = ValueError(detail)

    response = await client.post(f"{MATERIAL_URL}/complete", json={})

    assert response.status_code == 400
    assert response.json() == {"detail": detail}
    complete.complete.assert_not_awaited()


async def test_complete_material_that_is_missing_is_404(client, complete):
    complete.check.side_effect = NOT_FOUND

    response = await client.post(f"{MATERIAL_URL}/complete", json={})

    assert response.status_code == 404
    assert response.json() == NOT_FOUND_BODY
    complete.complete.assert_not_awaited()


async def test_complete_material_maps_a_lost_race_to_409(client, complete):
    complete.complete.side_effect = database.ConflictException(
        "Material is not being read"
    )

    response = await client.post(f"{MATERIAL_URL}/complete", json={})

    assert response.status_code == 409
    assert response.json() == {"detail": "ConflictError: Material is not being read"}


@pytest.mark.parametrize(
    "request_kwargs",
    [
        {},
        {"json": {"completed_at": "31.12.2026"}},
        {"json": {"started_at": "2026-01-01"}},
    ],
    ids=["no-body", "bad-date", "extra"],
)
async def test_complete_material_rejects_invalid_body(client, complete, request_kwargs):
    response = await client.post(f"{MATERIAL_URL}/complete", **request_kwargs)

    assert response.status_code == 422
    complete.check.assert_not_awaited()


@pytest.mark.parametrize(
    ("action", "db_function"),
    [("outline", "outline_material"), ("repeat", "repeat_material")],
)
class TestMaterialAction:
    async def test_runs_the_action(self, client, mocker, action, db_function):
        run = _patch(mocker, db_function, return_value=None)

        response = await client.post(f"{MATERIAL_URL}/{action}")

        assert response.status_code == 204
        assert response.content == b""
        run.assert_awaited_once_with(material_id=factories.MATERIAL_ID)

    @pytest.mark.parametrize(
        ("exc", "status_code", "detail"),
        [
            (NOT_FOUND, 404, "NotFoundError: Material not found"),
            (
                database.ConflictException("Material is not completed"),
                409,
                "ConflictError: Material is not completed",
            ),
        ],
        ids=["missing", "wrong-state"],
    )
    async def test_maps_database_errors(
        self, client, mocker, action, db_function, exc, status_code, detail
    ):
        _patch(mocker, db_function, side_effect=exc)

        response = await client.post(f"{MATERIAL_URL}/{action}")

        assert response.status_code == status_code
        assert response.json() == {"detail": detail}

    async def test_rejects_bad_uuid(self, client, mocker, action, db_function):
        run = _patch(mocker, db_function, return_value=None)

        response = await client.post(f"{BASE}/1/{action}")

        assert response.status_code == 422
        run.assert_not_awaited()


@pytest.fixture
def list_log_records(mocker):
    return mocker.patch.object(
        reading_log_db, "list_log_records", mocker.AsyncMock(return_value=[])
    )


@pytest.mark.parametrize(
    ("counts", "pages_read"),
    [([], 0), ([90], 90), ([1, 0, 1299], 1300), ([700, 700], 1400)],
    ids=["no-logs", "one-day", "with-zero-day", "more-than-material-pages"],
)
async def test_completion_info_sums_the_logs(
    client, get_material_api, list_log_records, counts, pages_read
):
    list_log_records.return_value = [
        factories.log_record(count=count, date=datetime.date(2026, 1, day))
        for day, count in enumerate(counts, 1)
    ]

    response = await client.get(f"{MATERIAL_URL}/completion-info")

    assert response.status_code == 200
    assert response.json() == {
        "material_pages": 1300,
        "material_type": "book",
        "pages_read": pages_read,
        "read_days": len(counts),
    }
    get_material_api.assert_awaited_once_with(material_id=factories.MATERIAL_ID)
    list_log_records.assert_awaited_once_with(material_id=factories.MATERIAL_ID)


async def test_completion_info_of_a_missing_material_is_404(
    client, get_material_api, list_log_records
):
    get_material_api.side_effect = NOT_FOUND

    response = await client.get(f"{MATERIAL_URL}/completion-info")

    assert response.status_code == 404
    assert response.json() == NOT_FOUND_BODY
    list_log_records.assert_not_awaited()


def test_static_routes_are_declared_before_the_material_id_route():
    paths = [route.path for route in materials_api.router.routes]

    for static in (
        "queue",
        "reading",
        "completed",
        "repeat",
        "authors",
        "tags",
        "titles",
        "is-reading",
    ):
        assert paths.index(f"/materials/{static}") < paths.index(
            "/materials/{material_id}"
        )


def test_requests_forbid_extra_fields():
    for model in (
        schemas.CreateMaterialRequest,
        schemas.UpdateMaterialRequest,
        schemas.StartMaterialRequest,
        schemas.CompleteMaterialRequest,
        schemas.ParseLinkRequest,
    ):
        assert model.model_config["extra"] == "forbid"
