import datetime
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from sqlalchemy.dialects import postgresql

from tracker.common import database, settings
from tracker.google_drive import db
from tracker.google_drive.db import DBSnapshot, TableSnapshot
from tracker.models import models


MATERIAL_ID = "3f1a3b2e-8c2a-4d6e-9f0a-1b2c3d4e5f60"
QUEUED_MATERIAL_ID = "0b9c2c51-41b5-4b0e-8a0b-7f0d1c2e3a4b"
TABLE_NAMES = [
    "materials",
    "reading_log",
    "notes",
    "cards",
    "repeats",
    "note_repeats_history",
]


class FakeConnection:
    def __init__(self) -> None:
        self.statements: list = []

    async def execute(self, stmt) -> None:
        self.statements.append(stmt)

    def inserts(self) -> list[tuple[str, list[int]]]:
        """Table name and the `count` values of every executed insert."""
        result = []
        for stmt in self.statements:
            params = stmt.compile(dialect=postgresql.dialect()).params
            counts = [
                value
                for key, value in params.items()
                if key.startswith("count_m") and value is not None
            ]
            result.append((stmt.table.name, counts))
        return result


def _log_rows(amount: int) -> list[dict]:
    return [{"count": index} for index in range(amount)]


class TestTableSnapshot:
    @pytest.mark.parametrize("amount", [0, 1, 3])
    def test_counter_is_the_number_of_rows(self, amount):
        snapshot = TableSnapshot(table_name="notes", rows=[{"n": 1}] * amount)

        assert snapshot.counter == amount


class TestDBSnapshot:
    def test_to_dict_maps_table_names_to_snapshots(self):
        notes = TableSnapshot(table_name="notes", rows=[{"note_number": 1}])
        cards = TableSnapshot(table_name="cards", rows=[])

        assert DBSnapshot(tables=[notes, cards]).to_dict() == {"notes": notes, "cards": cards}

    def test_to_dict_of_empty_snapshot(self):
        assert DBSnapshot(tables=[]).to_dict() == {}

    def test_to_dict_keeps_the_last_of_duplicated_tables(self):
        first = TableSnapshot(table_name="notes", rows=[{"note_number": 1}])
        last = TableSnapshot(table_name="notes", rows=[{"note_number": 2}])

        assert DBSnapshot(tables=[first, last]).to_dict() == {"notes": last}

    def test_from_empty_dump(self):
        assert DBSnapshot.from_dump({}) == DBSnapshot(tables=[])

    def test_from_dump_keeps_table_order_and_empty_tables(self):
        snapshot = DBSnapshot.from_dump({"notes": [], "materials": []})

        assert snapshot.tables == [
            TableSnapshot(table_name="notes", rows=[]),
            TableSnapshot(table_name="materials", rows=[]),
        ]

    def test_from_dump_parses_only_date_columns(self):
        dump = {
            "materials": [
                {
                    "material_id": MATERIAL_ID,
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

        assert snapshot["materials"].rows == [
            {
                "material_id": MATERIAL_ID,
                "title": "1 + 1",
                "authors": "2024-01-01",
                "added_at": datetime.datetime(2024, 1, 2, 3, 4, 5),  # noqa: DTZ001
                "pages": 42,
            },
        ]
        assert snapshot["reading_log"].rows == [{"date": datetime.date(2024, 1, 3), "count": 10}]
        assert snapshot["unknown_table"].rows == [{"value": "2024-01-05"}]

    @pytest.mark.parametrize(
        ("table", "column"),
        [
            ("materials", "added_at"),
            ("materials", "started_at"),
            ("materials", "completed_at"),
            ("notes", "added_at"),
            ("cards", "added_at"),
            ("repeats", "repeated_at"),
            ("note_repeats_history", "repeated_at"),
        ],
    )
    def test_from_dump_parses_every_datetime_column(self, table, column):
        dump = {table: [{column: "2024-01-02 03:04:05"}]}

        [row] = DBSnapshot.from_dump(dump).to_dict()[table].rows

        assert row == {column: datetime.datetime(2024, 1, 2, 3, 4, 5)}  # noqa: DTZ001

    def test_from_dump_folds_legacy_statuses_into_materials(self, caplog):
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

    def test_from_dump_keeps_material_status_columns_without_legacy_statuses(self):
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

    def test_from_dump_without_materials_drops_legacy_statuses(self):
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

    def test_from_dump_keeps_material_dates_without_matching_legacy_status(self):
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

    def test_from_dump_drops_columns_missing_from_schema(self):
        dump = {
            "materials": [{"material_id": MATERIAL_ID, "index": 1}],
            "unknown_table": [{"index": 1}],
        }

        snapshot = DBSnapshot.from_dump(dump).to_dict()

        assert snapshot["materials"].rows == [{"material_id": MATERIAL_ID}]
        assert snapshot["unknown_table"].rows == [{"index": 1}]

    def test_from_dump_does_not_mutate_the_dump(self):
        row = {"material_id": MATERIAL_ID, "added_at": "2024-01-02 03:04:05", "index": 1}
        dump = {"materials": [row], "unknown_table": [{"index": 1}]}

        snapshot = DBSnapshot.from_dump(dump).to_dict()

        assert row == {
            "material_id": MATERIAL_ID,
            "added_at": "2024-01-02 03:04:05",
            "index": 1,
        }
        assert snapshot["unknown_table"].rows[0] is not dump["unknown_table"][0]


class TestFoldLegacyStatuses:
    def test_dump_without_statuses_is_returned_as_is(self):
        dump = {"materials": [{"material_id": MATERIAL_ID}]}

        assert db._fold_legacy_statuses(dump) is dump

    def test_statuses_table_is_removed_and_other_tables_are_kept(self):
        notes = [{"note_id": "n"}]
        dump = {"notes": notes, "statuses": [], "materials": []}

        folded = db._fold_legacy_statuses(dump)

        assert folded == {"notes": notes, "materials": []}
        assert list(dump) == ["notes", "statuses", "materials"]

    def test_last_status_of_a_material_wins(self):
        dump = {
            "materials": [{"material_id": MATERIAL_ID}],
            "statuses": [
                {"material_id": MATERIAL_ID, "started_at": "first", "completed_at": None},
                {"material_id": MATERIAL_ID, "started_at": "second", "completed_at": "done"},
            ],
        }

        [material] = db._fold_legacy_statuses(dump)["materials"]

        assert material == {
            "material_id": MATERIAL_ID,
            "started_at": "second",
            "completed_at": "done",
        }

    def test_no_warning_when_every_status_has_a_material(self, caplog):
        dump = {
            "materials": [{"material_id": MATERIAL_ID}],
            "statuses": [{"material_id": MATERIAL_ID}],
        }

        with caplog.at_level(logging.WARNING, logger=settings.LOGGER_NAME):
            db._fold_legacy_statuses(dump)

        assert caplog.messages == []

    def test_every_orphan_status_is_counted(self, caplog):
        dump = {"statuses": [{"material_id": "a"}, {"material_id": "b"}]}

        with caplog.at_level(logging.WARNING, logger=settings.LOGGER_NAME):
            db._fold_legacy_statuses(dump)

        assert caplog.messages == ["2 legacy statuses reference missing materials, skipped"]


class TestFoldStatus:
    @pytest.mark.parametrize(
        ("material", "status", "expected"),
        [
            ({}, {}, {"started_at": None, "completed_at": None}),
            (
                {"started_at": "m1", "completed_at": "m2"},
                {},
                {"started_at": "m1", "completed_at": "m2"},
            ),
            (
                {"started_at": "m1", "completed_at": "m2"},
                {"started_at": "s1", "completed_at": "s2"},
                {"started_at": "s1", "completed_at": "s2"},
            ),
            (
                {"started_at": "m1", "completed_at": "m2"},
                {"started_at": "s1", "completed_at": None},
                {"started_at": "s1", "completed_at": None},
            ),
            (
                {"started_at": "m1"},
                {"completed_at": "s2"},
                {"started_at": "m1", "completed_at": "s2"},
            ),
        ],
        ids=[
            "nothing-known",
            "material-dates-kept",
            "status-overrides",
            "status-null-overrides",
            "mixed",
        ],
    )
    def test_status_dates_take_precedence(self, material, status, expected):
        assert db._fold_status(material, status) == expected

    def test_other_material_fields_are_kept_and_input_is_not_mutated(self):
        material = {"material_id": MATERIAL_ID, "title": "Title"}

        folded = db._fold_status(material, {"started_at": "s1", "status_id": "ignored"})

        assert folded == {
            "material_id": MATERIAL_ID,
            "title": "Title",
            "started_at": "s1",
            "completed_at": None,
        }
        assert material == {"material_id": MATERIAL_ID, "title": "Title"}


class TestDateColumns:
    @pytest.mark.parametrize(
        ("table", "expected"),
        [
            (
                models.Materials,
                {
                    "added_at": datetime.datetime,
                    "started_at": datetime.datetime,
                    "completed_at": datetime.datetime,
                },
            ),
            (models.ReadingLog, {"date": datetime.date}),
            (models.Notes, {"added_at": datetime.datetime}),
            (models.Cards, {"added_at": datetime.datetime}),
            (models.Repeats, {"repeated_at": datetime.datetime}),
            (models.NoteRepeatsHistory, {"repeated_at": datetime.datetime}),
        ],
        ids=TABLE_NAMES,
    )
    def test_date_and_datetime_columns_of_every_table(self, table, expected):
        assert db._date_columns(table) == expected

    def test_restored_tables_are_listed_in_insert_order(self):
        assert list(db.TABLES) == TABLE_NAMES
        assert [table.name for table in db.TABLES.values()] == TABLE_NAMES


class TestParseDate:
    def test_date_string(self):
        assert db._parse_date("2024-02-29", datetime.date) == datetime.date(2024, 2, 29)

    def test_datetime_string(self):
        parsed = db._parse_date("2024-02-29 23:59:59", datetime.datetime)

        assert parsed == datetime.datetime(2024, 2, 29, 23, 59, 59)  # noqa: DTZ001

    @pytest.mark.parametrize("value", [None, "", 0, 42], ids=repr)
    @pytest.mark.parametrize("python_type", [datetime.date, datetime.datetime])
    def test_non_string_and_empty_values_are_returned_as_is(self, value, python_type):
        assert db._parse_date(value, python_type) is value

    @pytest.mark.parametrize(
        ("value", "python_type"),
        [
            ("2024-01-02 03:04:05.123456", datetime.datetime),
            ("2024-01-02T03:04:05", datetime.datetime),
            ("2024-01-02", datetime.datetime),
            ("2024-01-02 03:04:05", datetime.date),
            ("2024-02-30", datetime.date),
            ("garbage", datetime.date),
        ],
        ids=[
            "microseconds",
            "iso-separator",
            "date-for-datetime-column",
            "datetime-for-date-column",
            "impossible-date",
            "garbage",
        ],
    )
    def test_other_formats_raise_value_error_current_behaviour(self, value, python_type):
        with pytest.raises(ValueError):  # noqa: PT011
            db._parse_date(value, python_type)


class TestGetDumpFilename:
    @pytest.fixture(autouse=True)
    def frozen_clock(self, mocker):
        mocker.patch.object(
            database,
            "utcnow",
            return_value=datetime.datetime(2024, 1, 2, 3, 4, 5, 678),  # noqa: DTZ001
        )

    def test_now_is_safe_for_file_names(self):
        assert db._get_now() == "2024-01-02_03-04-05"

    def test_default_prefix(self):
        assert db.get_dump_filename() == Path("data/tracker_2024-01-02_03-04-05.json")

    @pytest.mark.parametrize("prefix", ["last_dump", "", "дамп"])
    def test_custom_prefix(self, prefix):
        filename = db.get_dump_filename(prefix=prefix)

        assert filename == settings.DATA_DIR / f"{prefix}_2024-01-02_03-04-05.json"


class TestRestoreDb:
    async def test_empty_snapshot_is_rejected(self):
        conn = FakeConnection()

        with pytest.raises(ValueError, match="Snapshot is empty"):
            await db.restore_db(snapshot=DBSnapshot(tables=[]), conn=conn)

        assert conn.statements == []

    async def test_table_without_rows_is_skipped_with_a_warning(self, caplog):
        conn = FakeConnection()
        snapshot = DBSnapshot(tables=[TableSnapshot(table_name="reading_log", rows=[])])

        with caplog.at_level(logging.WARNING, logger=settings.LOGGER_NAME):
            await db.restore_db(snapshot=snapshot, conn=conn)

        assert conn.statements == []
        assert caplog.messages == [
            f"Table {name} not found in snapshot" for name in TABLE_NAMES
        ]

    @pytest.mark.parametrize(
        ("amount", "batches"),
        [
            (1, [1]),
            (999, [999]),
            pytest.param(
                1000,
                [1000],
                marks=pytest.mark.xfail(
                    strict=True,
                    reason=(
                        "BUG: tracker/google_drive/db.py:165 for exactly 1000 rows "
                        "a second insert with values([]) is executed"
                    ),
                ),
            ),
            (1001, [1000, 1]),
            (1999, [1000, 999]),
            pytest.param(
                2000,
                [1000, 1000],
                marks=pytest.mark.xfail(
                    strict=True,
                    reason=(
                        "BUG: tracker/google_drive/db.py:165 for a multiple of 1000 "
                        "rows a trailing insert with values([]) is executed"
                    ),
                ),
            ),
        ],
    )
    async def test_rows_are_inserted_in_batches_of_1000(self, amount, batches):
        conn = FakeConnection()
        snapshot = DBSnapshot(
            tables=[TableSnapshot(table_name="reading_log", rows=_log_rows(amount))],
        )

        await db.restore_db(snapshot=snapshot, conn=conn)

        inserts = conn.inserts()
        assert [len(counts) for _, counts in inserts] == batches
        assert [count for _, counts in inserts for count in counts] == list(range(amount))

    async def test_trailing_empty_batch_inserts_a_row_of_defaults_current_behaviour(self):
        conn = FakeConnection()
        snapshot = DBSnapshot(
            tables=[TableSnapshot(table_name="reading_log", rows=_log_rows(1000))],
        )

        await db.restore_db(snapshot=snapshot, conn=conn)

        compiled = conn.statements[-1].compile(dialect=postgresql.dialect())
        assert str(compiled) == (
            "INSERT INTO reading_log (log_id, date) VALUES (%(log_id)s::UUID, %(date)s)"
        )

    async def test_tables_are_inserted_in_dependency_order(self):
        conn = FakeConnection()
        snapshot = DBSnapshot(
            tables=[
                TableSnapshot(table_name=name, rows=[{"material_id": MATERIAL_ID}])
                for name in reversed(TABLE_NAMES)
            ],
        )

        await db.restore_db(snapshot=snapshot, conn=conn)

        assert [stmt.table.name for stmt in conn.statements] == TABLE_NAMES

    async def test_unknown_tables_are_ignored(self):
        conn = FakeConnection()
        snapshot = DBSnapshot(
            tables=[
                TableSnapshot(table_name="unknown_table", rows=[{"index": 1}]),
                TableSnapshot(table_name="reading_log", rows=_log_rows(2)),
            ],
        )

        await db.restore_db(snapshot=snapshot, conn=conn)

        assert conn.inserts() == [("reading_log", [0, 1])]


class TestSetSeqValue:
    @pytest.mark.parametrize(
        ("rows", "max_number"),
        [
            ([{"note_number": 7}], 7),
            ([{"note_number": 3}, {"note_number": 12}, {"note_number": 5}], 12),
            ([{"note_number": 3}, {"title": "no number"}], 3),
        ],
        ids=["single", "max-of-several", "row-without-number-counts-as-zero"],
    )
    async def test_notes_sequence_is_set_to_the_max_note_number(self, rows, max_number):
        conn = FakeConnection()

        await db.set_notes_seq_value(TableSnapshot(table_name="notes", rows=rows), conn)

        assert [str(stmt) for stmt in conn.statements] == [
            f"SELECT setval('notes_note_number_seq', {max_number}, true)",
        ]

    async def test_sequence_name_is_built_from_table_and_field(self):
        conn = FakeConnection()

        await db._set_seq_value(
            conn=conn,
            table_name="cards",
            field_name="card_number",
            rows=TableSnapshot(table_name="cards", rows=[{"card_number": 2}]),
        )

        assert [str(stmt) for stmt in conn.statements] == [
            "SELECT setval('cards_card_number_seq', 2, true)",
        ]

    @pytest.mark.xfail(
        strict=True,
        raises=ValueError,
        reason=(
            "BUG: tracker/google_drive/db.py:197 max() of an empty sequence when "
            "the snapshot holds no notes"
        ),
    )
    async def test_snapshot_without_notes_does_not_crash(self):
        conn = FakeConnection()

        await db.set_notes_seq_value(TableSnapshot(table_name="notes", rows=[]), conn)

        assert len(conn.statements) <= 1


class TestGetTablesAnalytics:
    async def test_counts_every_table_in_one_query(self, mocker):
        rows = [mocker.Mock(cnt=index) for index, _ in enumerate(TABLE_NAMES)]
        for row, name in zip(rows, TABLE_NAMES, strict=True):
            row.name = f"{name}_count"
        result = mocker.Mock()
        result.all.return_value = rows
        session = mocker.Mock(execute=mocker.AsyncMock(return_value=result))

        @asynccontextmanager
        async def open_session(**_kwargs):
            yield session

        mocker.patch.object(database, "session", open_session)

        analytics = await db.get_tables_analytics()

        assert analytics == {
            "materials_count": 0,
            "reading_log_count": 1,
            "notes_count": 2,
            "cards_count": 3,
            "repeats_count": 4,
            "note_repeats_history_count": 5,
        }
        [call] = session.execute.await_args_list
        assert str(call.args[0]) == "\nUNION\n".join(
            f"SELECT '{name}_count' AS name, COUNT(1) AS cnt FROM {name}"  # noqa: S608
            for name in TABLE_NAMES
        )

    async def test_no_rows_give_empty_analytics(self, mocker):
        result = mocker.Mock()
        result.all.return_value = []
        session = mocker.Mock(execute=mocker.AsyncMock(return_value=result))

        @asynccontextmanager
        async def open_session(**_kwargs):
            yield session

        mocker.patch.object(database, "session", open_session)

        assert await db.get_tables_analytics() == {}
