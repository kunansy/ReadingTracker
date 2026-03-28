import pytest

from tracker.materials import db as materials_db


class FakeResponse:
    def __init__(self, json_data, *, raise_for_status_exc: Exception | None = None):
        self._json_data = json_data
        self._raise_for_status_exc = raise_for_status_exc
        self.json_called = 0
        self.raise_for_status_called = 0

    async def json(self):
        self.json_called += 1
        return self._json_data

    def raise_for_status(self):
        self.raise_for_status_called += 1
        if self._raise_for_status_exc:
            raise self._raise_for_status_exc


class FakeSession:
    def __init__(self, response: FakeResponse):
        self._response = response
        self.get_calls: list[tuple[str, dict]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url: str, *, params: dict):
        self.get_calls.append((url, params))
        return self._response


@pytest.mark.parametrize(
    ("video_id", "duration", "expected_minutes"),
    [
        # real video ids, duration values are from mocked API payloads (no network)
        ("Y-wNpXtU_vg", "PT1H2M3S", 62),
        ("XUttZ838Tw0", "PT2M", 2),
        ("XUttZ838Tw0", "PT59S", 1),
        ("Y-wNpXtU_vg", "PT0S", 0),
        ("Y-wNpXtU_vg", "PT1H", 60),
        ("Y-wNpXtU_vg", "PT1H30M", 90),
        ("Y-wNpXtU_vg", "PT1M30S", 2),
    ],
)
async def test_parse_youtube_success(monkeypatch, video_id, duration, expected_minutes):
    monkeypatch.setattr(materials_db.settings, "YOUTUBE_API_URL", "https://example.test/youtube")
    monkeypatch.setattr(materials_db.settings, "YOUTUBE_API_KEY", "test-key")

    payload = {
        "items": [
            {
                "snippet": {"title": f"title-{video_id}", "channelTitle": "channel-1"},
                "contentDetails": {"duration": duration},
            },
        ],
    }
    resp = FakeResponse(payload)
    session = FakeSession(resp)

    def fake_client_session(*, timeout):
        return session

    monkeypatch.setattr(materials_db.aiohttp, "ClientSession", fake_client_session)

    result = await materials_db.parse_youtube(video_id)

    assert result.title == f"title-{video_id}", result.title
    assert result.authors == "channel-1", result.authors
    assert result.duration == expected_minutes, result.duration

    assert len(session.get_calls) == 1
    url, params = session.get_calls[0]
    assert url == "https://example.test/youtube"
    assert params == {
        "part": "snippet,contentDetails",
        "id": video_id,
        "key": "test-key",
    }
    assert resp.json_called == 1
    assert resp.raise_for_status_called == 1


async def test_parse_youtube_raises_on_http_error(monkeypatch):
    monkeypatch.setattr(materials_db.settings, "YOUTUBE_API_URL", "https://example.test/youtube")
    monkeypatch.setattr(materials_db.settings, "YOUTUBE_API_KEY", "test-key")

    class Boom(Exception):
        pass

    resp = FakeResponse({"items": []}, raise_for_status_exc=Boom("nope"))
    session = FakeSession(resp)

    monkeypatch.setattr(materials_db.aiohttp, "ClientSession", lambda *, timeout: session)

    with pytest.raises(Boom):
        await materials_db.parse_youtube("Y-wNpXtU_vg")

    # current implementation calls json() before raise_for_status()
    assert resp.json_called == 1
    assert resp.raise_for_status_called == 1


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"items": []},
        {"items": [{}]},
        {"items": [{"snippet": {}}]},
        {"items": [{"snippet": {"title": "t"}}]},
        {"items": [{"snippet": {"title": "t", "channelTitle": "c"}}]},
        {"items": [{"contentDetails": {"duration": "PT2M"}}]},
    ],
)
async def test_parse_youtube_invalid_payload_raises(monkeypatch, payload):
    monkeypatch.setattr(materials_db.settings, "YOUTUBE_API_URL", "https://example.test/youtube")
    monkeypatch.setattr(materials_db.settings, "YOUTUBE_API_KEY", "test-key")

    resp = FakeResponse(payload)
    session = FakeSession(resp)
    monkeypatch.setattr(materials_db.aiohttp, "ClientSession", lambda *, timeout: session)

    with pytest.raises((KeyError, IndexError, TypeError)):
        await materials_db.parse_youtube("XUttZ838Tw0")


@pytest.mark.integration
@pytest.mark.parametrize(
    "video_id, expected_title, expected_author, expected_duration", (
        ("Y-wNpXtU_vg", "Маргинал смотрит обзор Утопиана на Itpedia (Часть 1)", "Кирилл Кириллович", 36),
        ("XUttZ838Tw0", "Константин Владимиров — Распределение регистров", "Systems Meetups", 46),
    )
)
async def test_parse_youtube_real_api_opt_in(monkeypatch, video_id, expected_title, expected_author, expected_duration):
    result = await materials_db.parse_youtube(video_id, http_timeout=10)

    assert result.title == expected_title, result.title
    assert result.authors == expected_author, result.authors
    assert result.duration == expected_duration, result.duration
