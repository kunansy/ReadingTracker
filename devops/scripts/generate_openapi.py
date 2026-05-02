#!/usr/bin/env python3
import json
from pathlib import Path

from tracker.main import app


SPEC_PATH = Path('openapi.json')


def export():
    with SPEC_PATH.open('w') as f:
        json.dump(app.openapi(), f, indent=2)
    print("OpenAPI spec saved to", SPEC_PATH)


if __name__ == "__main__":
    export()

