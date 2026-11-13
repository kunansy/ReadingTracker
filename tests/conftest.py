"""Pin the whole configuration before `tracker` is imported.

`tracker.common.settings` reads the environment at import time and then clears it, and
`environs.read_env` never overrides a variable that is already set. Setting every variable
here keeps the developer's `.env` (and the database it points to) out of the test run.
"""

import os


TEST_ENVIRONMENT = {
    "TRACKER_URL": "http://tracker.test",
    "API_DEBUG": "false",
    "DB_HOST": "127.0.0.1",
    # nothing listens here: a test that reaches for the database fails instead of reading real data
    "DB_PORT": "1",
    "DB_NAME": "tracker_unit",
    "DB_USERNAME": "tracker",
    "DB_PASSWORD": "tracker",
    "DB_TIMEOUT": "5",
    "DB_ISOLATION_LEVEL": "REPEATABLE READ",
    "LOGGER_NAME": "ReadingTrackerTests",
    "LOGGER_LEVEL": "DEBUG",
    "DRIVE_CREDS": "{}",
    "MANTICORE_MYSQL_HOST": "127.0.0.1",
    "MANTICORE_MYSQL_PORT": "1",
    "MANTICORE_MYSQL_DB_NAME": "Manticore",
    "BACKUP_HOST": "127.0.0.1",
    "BACKUP_PORT": "1",
    "YOUTUBE_API_URL": "https://youtube.test/v3/videos",
    "YOUTUBE_API_KEY": "test-youtube-key",
    "KAFKA_HOST": "127.0.0.1",
    "KAFKA_PORT": "1",
    "KAFKA_REPEAT_NOTES_TOPIC": "repeat-notes-test",
    "KAFKA_CACHE_NOTES_TOPIC": "cache-notes-test",
    "KAFKA_CONNECT_TIMEOUT": "1",
    "EX_ENABLE_KAFKA_TO_NOTIFY": "false",
    "EX_DARKMODE_ENABLE": "15:00:00",
}

os.environ.update(TEST_ENVIRONMENT)
