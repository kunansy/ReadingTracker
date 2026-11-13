import datetime
import logging
import uuid

import pytest

from tests.integration import factories, helpers
from tracker.common import database, settings, sort_keys
from tracker.google_drive import db as drive_db
from tracker.models import models


MATERIAL_ID = "11111111-1111-4111-8111-111111111111"
SECOND_MATERIAL_ID = "22222222-2222-4222-8222-222222222222"
LOG_ID = "33333333-3333-4333-8333-333333333333"
NOTE_ID = "44444444-4444-4444-8444-444444444444"
SECOND_NOTE_ID = "55555555-5555-4555-8555-555555555555"
CARD_ID = "66666666-6666-4666-8666-666666666666"
REPEAT_ID = "77777777-7777-4777-8777-777777777777"
NOTE_REPEAT_ID = "88888888-8888-4888-8888-888888888888"

ADDED_AT = datetime.datetime(2024, 1, 1, 10, 20, 30)  # noqa: DTZ001
EMPTY_ANALYTICS = {
    "materials_count": 0,
    "reading_log_count": 0,
    "notes_count": 0,
    "cards_count": 0,
    "repeats_count": 0,
    "note_repeats_history_count": 0,
}


def _material(material_id: str, title: str, **columns) -> dict:
    return {
        "material_id": material_id,
        "title": title,
        "authors": "Лев Толстой",
        "pages": 300,
        "material_type": "book",
        "tags": "classic, russian",
        "link": None,
        "added_at": "2024-01-01 10:20:30",
        "is_outlined": True,
        "sort_key": sort_keys.material_sort_key(
            added_at=ADDED_AT,
            material_id=material_id,
        ),
        **columns,
    }


def _note(note_id: str, note_number: int, **columns) -> dict:
    return {
        "note_id": note_id,
        "note_number": note_number,
        "material_id": MATERIAL_ID,
        "link_id": None,
        "title": None,
        "content": "Содержимое заметки.",
        "added_at": "2024-01-02 03:04:05",
        "chapter": "2",
        "page": 15,
        "tags": ["тег", "tag"],
        "is_deleted": False,
        "sort_key": sort_keys.note_sort_key(
            material_id=MATERIAL_ID,
            chapter="2",
            page=15,
            note_id=note_id,
        ),
        **columns,
    }


def _dump() -> dict:
    return {
        "materials": [
            _material(
                MATERIAL_ID,
                "Война и мир",
                started_at="2024-01-04 00:00:00",
                completed_at="2024-02-05 00:00:00",
            ),
            _material(
                SECOND_MATERIAL_ID,
                "Queued",
                started_at=None,
                completed_at=None,
                is_outlined=False,
            ),
        ],
        "reading_log": [
            {
                "log_id": LOG_ID,
                "material_id": MATERIAL_ID,
                "count": 42,
                "date": "2024-01-05",
                "sort_key": sort_keys.reading_log_sort_key(
                    material_id=MATERIAL_ID,
                    date=datetime.date(2024, 1, 5),
                    log_id=LOG_ID,
                ),
            },
        ],
        "notes": [
            _note(NOTE_ID, 7, title="Заголовок"),
            _note(SECOND_NOTE_ID, 12, link_id=NOTE_ID, is_deleted=True, tags=[]),
        ],
        "cards": [
            {
                "card_id": CARD_ID,
                "material_id": MATERIAL_ID,
                "note_id": NOTE_ID,
                "question": "Вопрос?",
                "answer": None,
                "added_at": "2024-01-03 00:00:00",
                "sort_key": sort_keys.card_sort_key(
                    added_at=datetime.datetime(2024, 1, 3),  # noqa: DTZ001
                    card_id=CARD_ID,
                ),
            },
        ],
        "repeats": [
            {
                "repeat_id": REPEAT_ID,
                "material_id": MATERIAL_ID,
                "repeated_at": "2024-03-01 12:00:00",
            },
        ],
        "note_repeats_history": [
            {
                "repeat_id": NOTE_REPEAT_ID,
                "note_id": NOTE_ID,
                "user_id": 9_000_000_000,
                "repeated_at": "2024-03-02 13:00:00",
            },
        ],
    }


async def _restore(dump: dict) -> drive_db.DBSnapshot:
    snapshot = drive_db.DBSnapshot.from_dump(dump)
    async with database.transaction() as ses:
        await drive_db.restore_db(snapshot=snapshot, conn=ses)
    return snapshot


def _repeats(count: int) -> list[dict]:
    return [
        {
            "repeat_id": str(uuid.UUID(int=index + 1)),
            "material_id": MATERIAL_ID,
            "repeated_at": "2024-03-01 12:00:00",
        }
        for index in range(count)
    ]


async def test_restore_db_writes_every_table_of_the_snapshot():
    await _restore(_dump())

    assert await factories.fetch_row(models.Materials, uuid.UUID(MATERIAL_ID)) == {
        "material_id": uuid.UUID(MATERIAL_ID),
        "title": "Война и мир",
        "authors": "Лев Толстой",
        "pages": 300,
        "material_type": "book",
        "tags": "classic, russian",
        "link": None,
        "added_at": ADDED_AT,
        "is_outlined": True,
        "started_at": datetime.datetime(2024, 1, 4),  # noqa: DTZ001
        "completed_at": datetime.datetime(2024, 2, 5),  # noqa: DTZ001
        "sort_key": f"2024-01-01T10:20:30.000000$${MATERIAL_ID}",
    }
    queued = await factories.fetch_row(models.Materials, uuid.UUID(SECOND_MATERIAL_ID))
    assert (queued["title"], queued["started_at"], queued["completed_at"]) == (
        "Queued",
        None,
        None,
    )
    assert queued["is_outlined"] is False
    assert await factories.fetch_row(models.ReadingLog, uuid.UUID(LOG_ID)) == {
        "log_id": uuid.UUID(LOG_ID),
        "material_id": uuid.UUID(MATERIAL_ID),
        "count": 42,
        "date": datetime.date(2024, 1, 5),
        "sort_key": f"{MATERIAL_ID}$$2024-01-05$${LOG_ID}",
    }
    assert await factories.fetch_row(models.Notes, uuid.UUID(NOTE_ID)) == {
        "note_id": uuid.UUID(NOTE_ID),
        "note_number": 7,
        "material_id": uuid.UUID(MATERIAL_ID),
        "link_id": None,
        "title": "Заголовок",
        "content": "Содержимое заметки.",
        "added_at": datetime.datetime(2024, 1, 2, 3, 4, 5),  # noqa: DTZ001
        "chapter": "2",
        "page": 15,
        "tags": ["тег", "tag"],
        "is_deleted": False,
        "sort_key": f"{MATERIAL_ID}$$0000000002$$0000000015$${NOTE_ID}",
    }
    second_note = await factories.fetch_row(models.Notes, uuid.UUID(SECOND_NOTE_ID))
    assert second_note["note_number"] == 12
    assert second_note["link_id"] == uuid.UUID(NOTE_ID)
    assert second_note["is_deleted"] is True
    assert second_note["tags"] == []
    assert await factories.fetch_row(models.Cards, uuid.UUID(CARD_ID)) == {
        "card_id": uuid.UUID(CARD_ID),
        "material_id": uuid.UUID(MATERIAL_ID),
        "note_id": uuid.UUID(NOTE_ID),
        "question": "Вопрос?",
        "answer": None,
        "added_at": datetime.datetime(2024, 1, 3),  # noqa: DTZ001
        "sort_key": f"2024-01-03T00:00:00.000000$${CARD_ID}",
    }
    assert await factories.fetch_row(models.Repeats, uuid.UUID(REPEAT_ID)) == {
        "repeat_id": uuid.UUID(REPEAT_ID),
        "material_id": uuid.UUID(MATERIAL_ID),
        "repeated_at": datetime.datetime(2024, 3, 1, 12),  # noqa: DTZ001
    }
    assert await factories.fetch_row(
        models.NoteRepeatsHistory,
        uuid.UUID(NOTE_REPEAT_ID),
    ) == {
        "repeat_id": uuid.UUID(NOTE_REPEAT_ID),
        "note_id": uuid.UUID(NOTE_ID),
        "user_id": 9_000_000_000,
        "repeated_at": datetime.datetime(2024, 3, 2, 13),  # noqa: DTZ001
    }
    assert await drive_db.get_tables_analytics() == {
        "materials_count": 2,
        "reading_log_count": 1,
        "notes_count": 2,
        "cards_count": 1,
        "repeats_count": 1,
        "note_repeats_history_count": 1,
    }


async def test_note_numbers_continue_after_the_restored_maximum():
    snapshot = drive_db.DBSnapshot.from_dump(_dump())
    async with database.transaction() as ses:
        await drive_db.restore_db(snapshot=snapshot, conn=ses)
        await drive_db.set_notes_seq_value(snapshot.to_dict()["notes"], ses)

    note_id = await factories.insert_note(material_id=uuid.UUID(MATERIAL_ID))

    assert (await factories.fetch_row(models.Notes, note_id))["note_number"] == 13


async def test_note_numbers_collide_when_the_sequence_is_not_moved():
    await _restore({"notes": [_note(NOTE_ID, 1)]})

    # the sequence still stands at its start, so the next number is the restored one
    with pytest.raises(database.AlreadyExistsException):
        await factories.insert_note(material_id=uuid.UUID(MATERIAL_ID))


@pytest.mark.xfail(
    strict=True,
    reason="BUG: tracker/google_drive/db.py:197 max() over an empty notes snapshot raises "
    "ValueError, so a dump without notes cannot be restored",
)
async def test_set_notes_seq_value_with_no_notes_keeps_the_sequence():
    async with database.transaction() as ses:
        await drive_db.set_notes_seq_value(drive_db.TableSnapshot("notes", []), ses)

    note_id = await factories.insert_note(material_id=uuid.UUID(MATERIAL_ID))

    assert (await factories.fetch_row(models.Notes, note_id))["note_number"] == 1


async def test_set_notes_seq_value_rejects_rows_without_a_number_current_behaviour():
    notes = drive_db.TableSnapshot("notes", [{"note_id": NOTE_ID}])

    with pytest.raises(database.DatabaseException, match="out of bounds"):
        async with database.transaction() as ses:
            await drive_db.set_notes_seq_value(notes, ses)


async def test_restore_db_folds_legacy_statuses_into_materials():
    legacy_material = {
        key: value
        for key, value in _material(MATERIAL_ID, "Legacy", index=1_000_000).items()
        if key not in {"started_at", "completed_at"}
    }
    dump = {
        "materials": [
            legacy_material,
            {
                **legacy_material,
                "material_id": SECOND_MATERIAL_ID,
                "title": "Never started",
            },
        ],
        "statuses": [
            {
                "status_id": "7d1f6c1e-2f0b-4a8e-9c6d-5b4a3c2d1e0f",
                "material_id": MATERIAL_ID,
                "started_at": "2024-01-04 00:00:00",
                "completed_at": None,
            },
            {
                "status_id": "7d1f6c1e-2f0b-4a8e-9c6d-5b4a3c2d1e00",
                "material_id": str(uuid.UUID(int=99)),
                "started_at": "2024-01-04 00:00:00",
                "completed_at": "2024-01-05 00:00:00",
            },
        ],
    }
    dump["materials"][1]["sort_key"] = sort_keys.material_sort_key(
        added_at=ADDED_AT,
        material_id=SECOND_MATERIAL_ID,
    )

    await _restore(dump)

    started = await factories.fetch_row(models.Materials, uuid.UUID(MATERIAL_ID))
    never_started = await factories.fetch_row(
        models.Materials,
        uuid.UUID(SECOND_MATERIAL_ID),
    )
    assert started["started_at"] == datetime.datetime(2024, 1, 4)  # noqa: DTZ001
    assert started["completed_at"] is None
    assert (never_started["started_at"], never_started["completed_at"]) == (None, None)
    assert await factories.count_rows(models.Materials) == 2


async def test_restore_db_rejects_an_empty_snapshot():
    with pytest.raises(database.DatabaseException, match="Snapshot is empty"):
        await _restore({})

    assert await drive_db.get_tables_analytics() == EMPTY_ANALYTICS


async def test_restore_db_skips_missing_empty_and_unknown_tables():
    await _restore(
        {
            "repeats": _repeats(2),
            "notes": [],
            "unknown_table": [{"id": 1}],
        },
    )

    assert await drive_db.get_tables_analytics() == {
        **EMPTY_ANALYTICS,
        "repeats_count": 2,
    }


@pytest.mark.parametrize(
    "rows",
    [1, 999, 1001],
    ids=["one", "under-a-batch", "batch-plus-one"],
)
async def test_restore_db_inserts_every_row_in_batches(rows):
    await _restore({"repeats": _repeats(rows)})

    assert await factories.count_rows(models.Repeats) == rows


@pytest.mark.xfail(
    strict=True,
    reason="BUG: tracker/google_drive/db.py:165 a row count that is a multiple of 1000 makes "
    "the last batch empty, and INSERT ... VALUES () fails on the NOT NULL columns",
)
@pytest.mark.parametrize("rows", [1000, 2000], ids=["one-batch", "two-batches"])
async def test_restore_db_inserts_a_whole_number_of_batches(rows):
    await _restore({"repeats": _repeats(rows)})

    assert await factories.count_rows(models.Repeats) == rows


async def test_restore_db_is_rolled_back_as_a_whole_on_a_bad_table():
    dump = _dump()
    dump["cards"][0]["question"] = None

    with pytest.raises(database.DatabaseException):
        await _restore(dump)

    assert await drive_db.get_tables_analytics() == EMPTY_ANALYTICS


async def test_restore_db_into_a_database_with_the_same_rows_raises_already_exists():
    await _restore({"repeats": _repeats(1)})

    with pytest.raises(database.AlreadyExistsException):
        await _restore({"repeats": _repeats(1)})

    assert await factories.count_rows(models.Repeats) == 1


async def test_from_dump_rejects_timestamps_with_microseconds_current_behaviour():
    dump = {"repeats": [{**_repeats(1)[0], "repeated_at": "2024-03-01 12:00:00.123456"}]}

    # the legacy JSON dumps were written with settings.DATETIME_FORMAT, which has no fraction
    with pytest.raises(ValueError, match="unconverted data remains"):
        drive_db.DBSnapshot.from_dump(dump)


async def test_get_tables_analytics_on_an_empty_database_is_all_zero():
    assert await drive_db.get_tables_analytics() == EMPTY_ANALYTICS


async def test_get_tables_analytics_counts_every_row_including_deleted_notes():
    material_id = await factories.start_material()
    await factories.insert_material()
    note_id = await factories.insert_note(material_id=material_id)
    deleted = await factories.insert_note(material_id=material_id)
    await helpers.execute(
        models.Notes.update()
        .values(is_deleted=True)
        .where(models.Notes.c.note_id == deleted),
    )
    for days_ago in (1, 2, 3):
        await factories.insert_log(
            material_id=material_id,
            date=factories.days_ago(days_ago),
        )
    await factories.insert_card(material_id=material_id, note_id=note_id)
    await factories.insert_repeat(material_id=material_id, repeated_at=ADDED_AT)
    await factories.insert_repeat(material_id=material_id, repeated_at=ADDED_AT)
    await factories.insert_note_repeat(note_id=note_id, repeated_at=ADDED_AT)

    assert await drive_db.get_tables_analytics() == {
        "materials_count": 2,
        "reading_log_count": 3,
        "notes_count": 2,
        "cards_count": 1,
        "repeats_count": 2,
        "note_repeats_history_count": 1,
    }


def test_table_snapshot_counts_its_rows():
    assert drive_db.TableSnapshot("repeats", _repeats(3)).counter == 3
    assert drive_db.TableSnapshot("repeats", []).counter == 0


def test_dump_filename_carries_the_current_time(mocker):
    mocker.patch.object(database, "utcnow", return_value=helpers.NOW)

    assert (
        drive_db.get_dump_filename()
        == settings.DATA_DIR / "tracker_2024-03-15_12-30-45.json"
    )
    assert (
        drive_db.get_dump_filename(prefix="copy").name == "copy_2024-03-15_12-30-45.json"
    )


def test_from_dump_keeps_empty_and_null_dates():
    dump = {
        "materials": [
            {"material_id": MATERIAL_ID, "started_at": "", "completed_at": None},
        ],
    }

    [table] = drive_db.DBSnapshot.from_dump(dump).tables

    assert table.rows == [
        {"material_id": MATERIAL_ID, "started_at": "", "completed_at": None},
    ]


def test_from_dump_folds_statuses_without_a_warning_when_none_is_orphaned(caplog):
    dump = {
        "materials": [{"material_id": MATERIAL_ID}],
        "statuses": [
            {
                "material_id": MATERIAL_ID,
                "started_at": "2024-01-04 00:00:00",
                "completed_at": None,
            },
        ],
    }

    with caplog.at_level(logging.WARNING):
        [table] = drive_db.DBSnapshot.from_dump(dump).tables

    assert table.rows == [
        {
            "material_id": MATERIAL_ID,
            "started_at": datetime.datetime(2024, 1, 4),  # noqa: DTZ001
            "completed_at": None,
        },
    ]
    assert caplog.records == []
