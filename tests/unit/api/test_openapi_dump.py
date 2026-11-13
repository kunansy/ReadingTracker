import orjson

from tracker import openapi_dump
from tracker.common import settings


def test_dump_is_deterministic(tmp_path):
    first, second = tmp_path / "first.json", tmp_path / "second.json"

    openapi_dump.dump_openapi(first)
    openapi_dump.dump_openapi(second)

    assert first.read_bytes() == second.read_bytes()


def test_dump_pins_the_version_and_keeps_the_rest_of_info(tmp_path):
    path = tmp_path / "openapi.json"

    openapi_dump.dump_openapi(path)

    spec = orjson.loads(path.read_bytes())
    assert spec["info"] == {
        "title": "Reading Tracker",
        "description": "Reading queue, logging the reading, keep some notes",
        "version": "v1",
    }
    assert {"/api/v1/notes/search", "/api/v1/notes/graph"} <= spec["paths"].keys()


def test_dump_does_not_change_the_served_schema(tmp_path):
    openapi_dump.dump_openapi(tmp_path / "openapi.json")

    assert openapi_dump.app.openapi()["info"]["version"] == settings.API_VERSION


def test_dump_is_indented_sorted_and_newline_terminated(tmp_path):
    path = tmp_path / "openapi.json"

    openapi_dump.dump_openapi(path)

    raw = path.read_bytes()
    spec = orjson.loads(raw)
    assert raw.endswith(b"}\n")
    assert not raw.endswith(b"\n\n")
    assert (
        raw
        == orjson.dumps(spec, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS) + b"\n"
    )
    assert list(spec) == sorted(spec)


def test_dump_overwrites_an_existing_file(tmp_path):
    path = tmp_path / "openapi.json"
    path.write_text("stale")

    openapi_dump.dump_openapi(path)

    assert orjson.loads(path.read_bytes())["openapi"].startswith("3.")
