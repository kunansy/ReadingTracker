import datetime
import logging
import uuid

from tracker.common import settings, sort_keys
from tracker.google_drive.db import DBSnapshot, restore_db
from tracker.materials import db as materials_db


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
        "unknown_table": [{"value": "2024-01-05"}],
    }

    snapshot = DBSnapshot.from_dump(dump).to_dict()

    material = snapshot["materials"].rows[0]
    assert material["title"] == "1 + 1"
    assert material["authors"] == "2024-01-01"
    assert material["added_at"] == datetime.datetime(2024, 1, 2, 3, 4, 5)  # noqa: DTZ001
    assert material["pages"] == 42
    assert snapshot["reading_log"].rows[0]["date"] == datetime.date(2024, 1, 3)
    assert snapshot["unknown_table"].rows[0]["value"] == "2024-01-05"


MATERIAL_ID = "3f1a3b2e-8c2a-4d6e-9f0a-1b2c3d4e5f60"
QUEUED_MATERIAL_ID = "0b9c2c51-41b5-4b0e-8a0b-7f0d1c2e3a4b"


def test_from_dump_folds_legacy_statuses_into_materials(caplog):
    dump = {
        "materials": [
            {"material_id": MATERIAL_ID, "title": "Read"},
            {"material_id": QUEUED_MATERIAL_ID, "title": "Queued"},
        ],
        "statuses": [
            {
                "status_id": "7d1f6c1e-2f0b-4a8e-9c6d-5b4a3c2d1e0f",
                "material_id": MATERIAL_ID,
                "started_at": "2024-01-04 00:00:00",
                "completed_at": "2024-02-05 00:00:00",
            },
            {
                "status_id": "1e2d3c4b-5a69-4788-9a0b-c1d2e3f4a5b6",
                "material_id": "9a8b7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d",
                "started_at": "2024-01-01 00:00:00",
                "completed_at": None,
            },
        ],
    }

    with caplog.at_level(logging.WARNING, logger=settings.LOGGER_NAME):
        snapshot = DBSnapshot.from_dump(dump).to_dict()

    assert "1 legacy statuses reference missing materials, skipped" in caplog.messages
    assert "statuses" not in snapshot
    read, queued = snapshot["materials"].rows
    assert read["started_at"] == datetime.datetime(2024, 1, 4)  # noqa: DTZ001
    assert read["completed_at"] == datetime.datetime(2024, 2, 5)  # noqa: DTZ001
    assert queued["started_at"] is None
    assert queued["completed_at"] is None


def test_from_dump_keeps_material_status_columns_without_legacy_statuses():
    dump = {
        "materials": [
            {
                "material_id": MATERIAL_ID,
                "started_at": "2024-01-04 00:00:00",
                "completed_at": None,
            },
        ],
    }

    [material] = DBSnapshot.from_dump(dump).to_dict()["materials"].rows

    assert material["started_at"] == datetime.datetime(2024, 1, 4)  # noqa: DTZ001
    assert material["completed_at"] is None


def test_from_dump_without_materials_drops_legacy_statuses():
    dump = {
        "statuses": [
            {
                "status_id": "7d1f6c1e-2f0b-4a8e-9c6d-5b4a3c2d1e0f",
                "material_id": MATERIAL_ID,
                "started_at": "2024-01-04 00:00:00",
                "completed_at": None,
            },
        ],
    }

    snapshot = DBSnapshot.from_dump(dump).to_dict()

    assert "statuses" not in snapshot
    assert snapshot["materials"].rows == []


def test_from_dump_keeps_material_dates_without_matching_legacy_status():
    dump = {
        "materials": [
            {
                "material_id": MATERIAL_ID,
                "started_at": "2024-01-04 00:00:00",
                "completed_at": "2024-02-05 00:00:00",
            },
        ],
        "statuses": [],
    }

    [material] = DBSnapshot.from_dump(dump).to_dict()["materials"].rows

    assert material["started_at"] == datetime.datetime(2024, 1, 4)  # noqa: DTZ001
    assert material["completed_at"] == datetime.datetime(2024, 2, 5)  # noqa: DTZ001


async def test_restore_legacy_dump_folds_statuses_into_materials(shared_session):
    material_id = str(uuid.uuid4())
    added_at = "2024-01-01 00:00:00"
    dump = {
        "materials": [
            {
                "material_id": material_id,
                "index": 1_000_000,
                "title": f"Legacy material {material_id}",
                "authors": "Author",
                "pages": 10,
                "material_type": "book",
                "tags": None,
                "link": None,
                "added_at": added_at,
                "is_outlined": False,
                "sort_key": sort_keys.material_sort_key(
                    added_at=datetime.datetime(2024, 1, 1),  # noqa: DTZ001
                    material_id=material_id,
                ),
            },
        ],
        "statuses": [
            {
                "status_id": "7d1f6c1e-2f0b-4a8e-9c6d-5b4a3c2d1e0f",
                "material_id": material_id,
                "started_at": "2024-01-04 00:00:00",
                "completed_at": "2024-02-05 00:00:00",
            },
        ],
    }

    await restore_db(snapshot=DBSnapshot.from_dump(dump), conn=shared_session)

    material = await materials_db.get_material_api(material_id=uuid.UUID(material_id))
    assert material.started_at == datetime.datetime(2024, 1, 4)  # noqa: DTZ001
    assert material.completed_at == datetime.datetime(2024, 2, 5)  # noqa: DTZ001
