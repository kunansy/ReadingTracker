import orjson

from tracker.openapi_dump import SPEC_VERSION, dump_openapi


def test_dump_openapi_is_pinned_and_deterministic(tmp_path):
    first, second = tmp_path / "first.json", tmp_path / "second.json"

    dump_openapi(first)
    dump_openapi(second)

    assert first.read_bytes() == second.read_bytes()
    spec = orjson.loads(first.read_bytes())
    assert spec["info"]["version"] == SPEC_VERSION
    assert {"/api/v1/notes/search", "/api/v1/notes/graph"} <= spec["paths"].keys()
