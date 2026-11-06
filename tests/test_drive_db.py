import datetime

from tracker.google_drive.db import DBSnapshot


def test_from_dump_parses_only_date_columns():
    dump = {
        "materials": [
            {
                "material_id": "3f1a3b2e-8c2a-4d6e-9f0a-1b2c3d4e5f60",
                "title": "1 + 1",
                "authors": "2024-01-01",
                "added_at": "2024-01-02 03:04:05",
                "pages": 42,
            },
        ],
        "reading_log": [{"date": "2024-01-03", "count": 10}],
        "statuses": [{"started_at": "2024-01-04 00:00:00", "completed_at": None}],
        "unknown_table": [{"value": "2024-01-05"}],
    }

    snapshot = DBSnapshot.from_dump(dump).to_dict()

    material = snapshot["materials"].rows[0]
    assert material["title"] == "1 + 1"
    assert material["authors"] == "2024-01-01"
    assert material["added_at"] == datetime.datetime(2024, 1, 2, 3, 4, 5)  # noqa: DTZ001
    assert material["pages"] == 42
    assert snapshot["reading_log"].rows[0]["date"] == datetime.date(2024, 1, 3)
    assert snapshot["statuses"].rows[0]["completed_at"] is None
    assert snapshot["unknown_table"].rows[0]["value"] == "2024-01-05"
