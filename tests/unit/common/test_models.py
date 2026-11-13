import datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest
import sqlalchemy
import uuid6
from sqlalchemy import Integer, Unicode
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from tracker.models import enums, models


MS = 1_000_000


def _compile(element) -> str:
    compiled = element.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True},
    )
    return " ".join(str(compiled).split())


@pytest.fixture
def uuid_clock(mocker, monkeypatch):
    # uuid7 never goes back in time, so the test must start from a clean counter
    monkeypatch.setattr(uuid6, "_last_v7_timestamp", None)
    return mocker.patch.object(uuid6.time, "time_ns")


def test_generate_id_is_a_uuid7_string(uuid_clock):
    uuid_clock.return_value = 1_700_000_000_123 * MS

    result = models.generate_id()

    assert isinstance(result, str)
    parsed = UUID(result)
    assert str(parsed) == result
    assert parsed.version == 7
    assert parsed.variant == "specified in RFC 4122"


def test_generate_id_starts_with_the_millisecond_timestamp(uuid_clock):
    uuid_clock.return_value = 1_700_000_000_123 * MS + 999_999

    result = models.generate_id()

    assert UUID(result).int >> 80 == 1_700_000_000_123
    assert result.startswith("018bcfe5-687b-7")


def test_generate_id_is_ordered_by_time(uuid_clock):
    uuid_clock.side_effect = [1_000 * MS, 1_001 * MS, 2_000 * MS, 10**12 * MS]

    ids = [models.generate_id() for _ in range(4)]

    assert ids == sorted(ids)
    assert len(set(ids)) == 4


def test_generate_id_stays_ordered_within_one_millisecond(uuid_clock):
    uuid_clock.return_value = 1_700_000_000_123 * MS

    ids = [models.generate_id() for _ in range(50)]

    assert ids == sorted(ids)
    assert len(set(ids)) == 50


def test_generate_id_stays_ordered_when_the_clock_goes_back(uuid_clock):
    uuid_clock.side_effect = [2_000 * MS, 1_000 * MS]

    first, second = models.generate_id(), models.generate_id()

    assert first < second


def test_utc_now_is_naive_utc(mocker):
    clock = mocker.Mock()
    clock.now.return_value = datetime.datetime(2024, 2, 29, 23, 59, 59, 1, datetime.UTC)
    mocker.patch.object(
        models,
        "datetime",
        SimpleNamespace(datetime=clock, UTC=datetime.UTC),
    )

    result = models._utc_now()

    clock.now.assert_called_once_with(datetime.UTC)
    assert result == datetime.datetime(2024, 2, 29, 23, 59, 59, 1)
    assert result.tzinfo is None


def test_column_is_not_nullable_by_default():
    column = models.Column("title", Unicode(10))

    assert column.nullable is False
    assert column.name == "title"


@pytest.mark.parametrize("nullable", [True, False])
def test_column_keeps_explicit_nullable(nullable):
    assert models.Column("title", Unicode(10), nullable=nullable).nullable is nullable


def test_column_passes_other_options():
    column = models.Column("pages", Integer, default=7, index=True, comment="c")

    assert column.default.arg == 7
    assert column.index is True
    assert column.comment == "c"


def test_primary_key_defaults_to_generated_uuid():
    column = models.PrimaryKey("some_id")

    assert column.primary_key is True
    assert column.nullable is False
    assert column.type.__class__ is postgresql.UUID
    assert column.default.arg.__wrapped__ is models.generate_id


def test_primary_key_keeps_explicit_type_and_default():
    column = models.PrimaryKey("some_id", Integer, default=1)

    assert column.primary_key is True
    assert isinstance(column.type, Integer)
    assert column.default.arg == 1


def test_primary_key_cannot_be_declared_non_primary():
    assert models.PrimaryKey("some_id", primary_key=False).primary_key is True


def test_serial_type_compiles_to_serial():
    assert models.Serial().get_col_spec() == "serial"
    assert models.Serial().get_col_spec(anything=1) == "serial"
    assert models.Serial.cache_ok is True


def test_sort_key_column():
    column = models.SortKey()

    assert column.name == "sort_key"
    assert column.nullable is False
    assert column.unique is True
    assert isinstance(column.type, Unicode)
    assert column.type.length == 512
    assert column.type.collation == "C"


def test_sort_key_returns_a_new_column_each_time():
    assert models.SortKey() is not models.SortKey()


def test_metadata_tables():
    assert sorted(models.metadata.tables) == [
        "cards",
        "materials",
        "note_repeats_history",
        "notes",
        "reading_log",
        "repeats",
    ]


@pytest.mark.parametrize(
    ("table", "primary_key"),
    [
        (models.Materials, "material_id"),
        (models.ReadingLog, "log_id"),
        (models.Notes, "note_id"),
        (models.Cards, "card_id"),
        (models.Repeats, "repeat_id"),
        (models.NoteRepeatsHistory, "repeat_id"),
    ],
    ids=lambda value: getattr(value, "name", value),
)
def test_every_table_has_a_generated_uuid_primary_key(table, primary_key):
    [column] = table.primary_key.columns

    assert column.name == primary_key
    assert column.default.arg.__wrapped__ is models.generate_id


@pytest.mark.parametrize(
    "table",
    [models.Materials, models.ReadingLog, models.Notes, models.Cards],
    ids=lambda table: table.name,
)
def test_listed_tables_have_unique_c_collated_sort_key(table):
    column = table.c.sort_key

    assert column.unique is True
    assert column.nullable is False
    assert column.type.collation == "C"


def test_nullable_columns():
    nullable = {
        f"{table.name}.{column.name}"
        for table in models.metadata.tables.values()
        for column in table.columns
        if column.nullable
    }

    assert nullable == {
        "materials.tags",
        "materials.link",
        "materials.started_at",
        "materials.completed_at",
        "notes.link_id",
        "notes.title",
        "notes.tags",
        "cards.answer",
    }


def test_notes_table_ddl():
    assert _compile(CreateTable(models.Notes)) == (
        "CREATE TABLE notes ( "
        "note_id UUID NOT NULL, "
        "note_number serial NOT NULL, "
        "material_id UUID NOT NULL, "
        "link_id UUID, "
        "title VARCHAR(4096), "
        "content VARCHAR(65536) NOT NULL, "
        "added_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, "
        "chapter VARCHAR(256) NOT NULL, "
        "page INTEGER NOT NULL, "
        "tags JSONB, "
        "is_deleted BOOLEAN NOT NULL, "
        'sort_key VARCHAR(512) COLLATE "C" NOT NULL, '
        "PRIMARY KEY (note_id), "
        "CONSTRAINT uix_notes_note_number UNIQUE (note_number) DEFERRABLE, "
        "UNIQUE (title), "
        "UNIQUE (sort_key) )"
    )


def test_reading_log_table_ddl():
    assert _compile(CreateTable(models.ReadingLog)) == (
        "CREATE TABLE reading_log ( "
        "log_id UUID NOT NULL, "
        "material_id UUID NOT NULL, "
        "count INTEGER NOT NULL, "
        "date DATE NOT NULL, "
        'sort_key VARCHAR(512) COLLATE "C" NOT NULL, '
        "PRIMARY KEY (log_id), "
        "CONSTRAINT uix_reading_log UNIQUE (material_id, date), "
        "UNIQUE (sort_key) )"
    )


def _create_index_sql(table: sqlalchemy.Table) -> set[str]:
    return {_compile(sqlalchemy.schema.CreateIndex(index)) for index in table.indexes}


def test_materials_listing_indexes():
    assert _create_index_sql(models.Materials) == {
        "CREATE INDEX ix_materials_completed_at_sort_key ON materials "
        "(completed_at, sort_key) WHERE completed_at IS NOT NULL",
        "CREATE INDEX ix_materials_started_at_sort_key ON materials "
        "(started_at, sort_key) WHERE started_at IS NOT NULL",
    }


def test_reading_log_listing_index():
    assert _create_index_sql(models.ReadingLog) == {
        "CREATE INDEX ix_reading_log_material_id ON reading_log (material_id)",
        "CREATE INDEX ix_reading_log_date_sort_key ON reading_log (date, sort_key)",
    }


def test_notes_links_index():
    assert (
        "CREATE INDEX ix_notes_link_id_note_number_sort_key ON notes "
        "(link_id, note_number, sort_key)"
    ) in _create_index_sql(models.Notes)


def test_python_side_column_defaults():
    defaults = {
        f"{table.name}.{column.name}": column.default.arg
        for table in models.metadata.tables.values()
        for column in table.columns
        if column.default is not None
        and not column.primary_key
        and not column.default.is_callable
    }

    assert defaults == {
        "materials.material_type": enums.MaterialTypesEnum.book,
        "materials.is_outlined": False,
        "notes.is_deleted": False,
    }


@pytest.mark.parametrize(
    "column",
    [
        models.Materials.c.added_at,
        models.Notes.c.added_at,
        models.Cards.c.added_at,
        models.Repeats.c.repeated_at,
        models.NoteRepeatsHistory.c.repeated_at,
    ],
    ids=lambda column: f"{column.table.name}.{column.name}",
)
def test_timestamp_columns_default_to_utc_now(column):
    assert column.default.arg.__wrapped__ is models._utc_now


def test_reading_log_date_defaults_to_a_datetime_current_behaviour(mocker):
    mocker.patch.object(
        models,
        "datetime",
        SimpleNamespace(
            datetime=SimpleNamespace(
                now=lambda tz: datetime.datetime(2024, 1, 2, 3, 4, 5, tzinfo=tz),
            ),
            UTC=datetime.UTC,
        ),
    )
    default = models.ReadingLog.c.date.default

    assert isinstance(models.ReadingLog.c.date.type, sqlalchemy.Date)
    assert default.arg.__wrapped__ is models._utc_now
    assert default.arg(None) == datetime.datetime(2024, 1, 2, 3, 4, 5)


@pytest.mark.parametrize(
    ("condition", "expected"),
    [
        (models.MATERIAL_IS_QUEUED, "materials.started_at IS NULL"),
        (models.MATERIAL_IS_STARTED, "materials.started_at IS NOT NULL"),
        (models.MATERIAL_IS_COMPLETED, "materials.completed_at IS NOT NULL"),
        (
            models.MATERIAL_IS_READING,
            "materials.started_at IS NOT NULL AND materials.completed_at IS NULL",
        ),
    ],
    ids=["queued", "started", "completed", "reading"],
)
def test_material_state_conditions(condition, expected):
    assert _compile(condition) == expected


def test_max_chapter_length_matches_the_column():
    assert models.Notes.c.chapter.type.length == models.MAX_CHAPTER_LENGTH == 256


def test_material_types_enum_values():
    assert [(member.name, member.value) for member in enums.MaterialTypesEnum] == [
        ("book", "book"),
        ("article", "article"),
        ("course", "course"),
        ("lecture", "lecture"),
        ("audiobook", "audiobook"),
    ]


def test_material_types_enum_members_are_strings():
    assert enums.MaterialTypesEnum.book == "book"
    assert str(enums.MaterialTypesEnum.audiobook) == "audiobook"
    assert f"{enums.MaterialTypesEnum.course}" == "course"


def test_material_types_enum_lookup_by_value():
    assert enums.MaterialTypesEnum("lecture") is enums.MaterialTypesEnum.lecture


@pytest.mark.parametrize("value", ["Book", "", "podcast", None], ids=repr)
def test_material_types_enum_rejects_unknown_value(value):
    with pytest.raises(ValueError):
        enums.MaterialTypesEnum(value)


def test_means_alias_describes_decimal_per_type():
    means: enums.MEANS = {enums.MaterialTypesEnum.book: Decimal("1.5")}

    assert enums.MEANS.__value__ == dict[enums.MaterialTypesEnum, Decimal]
    assert means[enums.MaterialTypesEnum("book")] == Decimal("1.5")
