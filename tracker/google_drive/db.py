import datetime
from pathlib import Path
from typing import NamedTuple
from uuid import UUID

import sqlalchemy.sql as sa
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.common import database, settings
from tracker.common.logger import logger
from tracker.models import models


JSON_FIELD_TYPES = str | int
DATE_TYPES = datetime.date | datetime.datetime | str
DUMP_TYPE = dict[str, list[dict[str, JSON_FIELD_TYPES]]]


class TableSnapshot(NamedTuple):
    # TODO: use a pydantic model
    table_name: str
    rows: list[dict[str, DATE_TYPES | JSON_FIELD_TYPES]]

    @property
    def counter(self) -> int:
        return len(self.rows)


class DBSnapshot(NamedTuple):
    tables: list[TableSnapshot]

    def to_dict(self) -> dict[str, TableSnapshot]:
        return {
            str(table_snapshot.table_name): table_snapshot
            for table_snapshot in self.tables
        }

    @classmethod
    def from_dump(cls, dump_data: DUMP_TYPE) -> "DBSnapshot":
        tables = []
        for table_name, values in dump_data.items():
            rows = [
                {key: _convert_str_to_date(value) for key, value in row.items()}
                for row in values
            ]
            tables += [TableSnapshot(table_name=table_name, rows=rows)]

        return DBSnapshot(tables=tables)


TABLES = {
    models.Materials.name: models.Materials,
    models.Statuses.name: models.Statuses,
    models.ReadingLog.name: models.ReadingLog,
    models.Notes.name: models.Notes,
    models.Cards.name: models.Cards,
    models.Repeats.name: models.Repeats,
    models.NoteRepeatsHistory.name: models.NoteRepeatsHistory,
}


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
        return True  # noqa: TRY300
    except ValueError:
        return False


def _contains_letter(value: str) -> bool:
    return any(symbol.isalpha() for symbol in value)


def _convert_str_to_date(value: JSON_FIELD_TYPES) -> JSON_FIELD_TYPES | DATE_TYPES:
    if (
        not value
        or not isinstance(value, str)
        or _is_uuid(value)
        or _contains_letter(value)
        or value.isdigit()
        or value == "-"
    ):
        return value

    try:
        return datetime.datetime.strptime(value, settings.DATETIME_FORMAT)  # noqa: DTZ007
    except Exception:  # noqa: S110
        pass

    try:
        return datetime.datetime.strptime(value, settings.DATE_FORMAT).date()  # noqa: DTZ007
    except Exception:  # noqa: S110
        pass

    raise ValueError(f"Invalid date format: {value!r}")


def _get_now() -> str:
    return (
        database.utcnow()
        .strftime(settings.DATETIME_FORMAT)
        .replace(" ", "_")
        .replace(":", "-")
    )


def get_dump_filename(*, prefix: str = "tracker") -> Path:
    filename = f"{prefix}_{_get_now()}.json"
    return settings.DATA_DIR / filename


async def restore_db(*, snapshot: DBSnapshot, conn: AsyncSession) -> None:
    if not snapshot.tables:
        raise ValueError("Snapshot is empty")

    snapshot_dict = snapshot.to_dict()

    # order of tables matters
    for table_name, table in TABLES.items():
        if not (table_dict := snapshot_dict.get(table_name)) or not table_dict.rows:
            # the table was empty for example
            logger.warning("Table %s not found in snapshot", table_name)
            continue

        values = table_dict.rows
        stmt = table.insert().values(values)
        await conn.execute(stmt)

        logger.info("%s: %s rows inserted", table.name, len(values))


async def get_tables_analytics() -> dict[str, int]:
    table_names = list(TABLES.keys())

    query = (
        [
            f"SELECT '{table}' AS name, COUNT(1) AS cnt FROM {table} UNION"  # noqa: S608
            for table in table_names[:-1]
        ]
        + [f"SELECT '{table_names[-1]}' AS name, COUNT(1) AS cnt FROM {table_names[-1]}"]  # noqa: S608
    )

    query_str = "\n".join(query)
    stmt = sa.text(query_str)

    async with database.session() as ses:
        res = (await ses.execute(stmt)).mappings().all()

    return {r.name: r.cnt for r in res}


async def _set_seq_value(
    *,
    conn: AsyncSession,
    table_name: str,
    field_name: str,
    rows: TableSnapshot,
) -> None:
    # TODO: iterate over table and find Serial fields
    max_note_number = max(row.get(field_name, 0) for row in rows.rows)
    seq_name = f"{table_name}_{field_name}_seq"

    query = f"SELECT setval('{seq_name}', {max_note_number}, true)"
    await conn.execute(sa.text(query))


async def set_notes_seq_value(notes: TableSnapshot, conn: AsyncSession) -> None:
    model = models.Notes

    await _set_seq_value(
        conn=conn,
        table_name=model.name,
        field_name=model.c.note_number.name,
        rows=notes,
    )


async def set_materials_seq_value(materials: TableSnapshot, conn: AsyncSession) -> None:
    model = models.Materials

    await _set_seq_value(
        conn=conn,
        table_name=model.name,
        field_name=model.c.index.name,
        rows=materials,
    )


async def create_repeat_notes_matview(conn: AsyncSession) -> None:
    query = """
    CREATE MATERIALIZED VIEW IF NOT EXISTS mvw_repeat_notes AS
        WITH repeated_notes_freq AS (
            SELECT note_id, COUNT(1)
            FROM note_repeats_history
            GROUP BY note_id
        ),
        all_notes_freq AS (
            SELECT
                n.material_id,
                n.note_id AS note_id,
                COALESCE(s.count, 0) AS count,
                COUNT(1) OVER () AS total
            FROM notes n
            LEFT JOIN repeated_notes_freq s USING(note_id)
            WHERE NOT n.is_deleted
        ),
        min_freq AS (
            SELECT count
            FROM all_notes_freq
            ORDER BY count
            LIMIT 1
        ),
        sample_notes AS (
            SELECT
                n.note_id,
                n.material_id,
                n.page,
                n.chapter,
                n.title,
                n.content,
                n.added_at,
                f.total AS total_notes_count,
                -- m.total AS total_freq_count,
                m.count AS min_repeat_freq
            FROM all_notes_freq f
            JOIN min_freq m ON f.count = m.count
            JOIN notes n ON f.note_id = n.note_id
        ),
        last_repeat AS (
            SELECT
                m.material_id,
                r.repeated_at,
                COUNT(1) OVER (PARTITION BY r.material_id) AS repeats_count
            FROM sample_notes n
            JOIN materials m USING(material_id)
            JOIN repeats r USING(material_id)
            ORDER BY r.repeated_at DESC
            LIMIT 1
        )
        SELECT
            n.note_id,
            m.material_id,
            m.title AS material_title,
            m.authors AS material_authors,
            m.material_type AS material_type,
            n.content,
            n.added_at,
            n.chapter,
            n.page,
            m.pages AS material_pages,
            n.total_notes_count AS total_notes_count,
            n.min_repeat_freq AS min_repeat_freq,
            CASE
                -- in this case the note have no material
                WHEN m IS NULL THEN 'completed'
                WHEN s IS NULL THEN 'queue'
                WHEN s.completed_at IS NULL THEN 'reading'
                ELSE 'completed'
            END AS material_status,
            r.repeated_at,
            r.repeats_count
        FROM
            sample_notes n
        LEFT JOIN materials m ON n.material_id = m.material_id
        LEFT JOIN statuses s ON s.material_id = m.material_id
        LEFT JOIN last_repeat r ON r.material_id = s.material_id
    WITH NO DATA;
    """

    await conn.execute(sa.text(query))
