"""Credentials for the tests that call real third-party services.

`tests/conftest.py` pins `YOUTUBE_API_KEY` / `YOUTUBE_API_URL` to dummies and
`tracker.common.settings` clears `os.environ` on import, so the real key is taken from
dedicated variables and captured here, before `tracker` is imported.
"""

import os


REAL_YOUTUBE_API_KEY = os.environ.get("NETWORK_YOUTUBE_API_KEY")
REAL_YOUTUBE_API_URL = os.environ.get(
    "NETWORK_YOUTUBE_API_URL",
    "https://youtube.googleapis.com/youtube/v3/videos",
)
