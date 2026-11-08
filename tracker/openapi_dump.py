import argparse
from pathlib import Path

import orjson

from tracker.main import app


# Pinned instead of settings.API_VERSION so release bumps do not show up as spec drift.
SPEC_VERSION = "v1"


def dump_openapi(path: Path) -> None:
    schema = app.openapi()
    schema = {**schema, "info": {**schema["info"], "version": SPEC_VERSION}}
    path.write_bytes(
        orjson.dumps(schema, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS) + b"\n",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dump the OpenAPI spec to a file")
    parser.add_argument("output", type=Path)
    dump_openapi(parser.parse_args().output)
