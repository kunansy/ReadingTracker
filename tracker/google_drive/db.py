import datetime
from pathlib import Path
from typing import Final, NamedTuple

import sqlalchemy.sql as sa
from sqlalchemy import Date, DateTime, Table
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.common import database, settings
from tracker.common.logger import logger
from tracker.models import models


JSON_FIELD_TYPES = str | int
DATE_TYPES = datetime.date | datetime.datetime | str
DUMP_TYPE = dict[str, list[dict[str, JSON_FIELD_TYPES]]]
# Dumps made before revision 0004 keep the material start and completion dates here.
LEGACY_STATUSES_TABLE: Final[str] = "statuses"


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
    def from_dump(cls, dump_data: DUMP_TYPE) -> DBSnapshot:
        tables = []
        for table_name, values in _fold_legacy_statuses(dump_data).items():
            if (table := TABLES.get(table_name)) is None:
                rows = [dict(row) for row in values]
                tables.append(TableSnapshot(table_name=table_name, rows=rows))
                continue

            date_columns = _date_columns(table)
            known_columns = frozenset(table.columns.keys())
            rows = [
                {
                    key: _parse_date(value, date_columns[key])
                    if key in date_columns
                    else value
                    for key, value in row.items()
                    if key in known_columns
                }
                for row in values
            ]
            tables.append(TableSnapshot(table_name=table_name, rows=rows))

        return DBSnapshot(tables=tables)


TABLES = {
    models.Materials.name: models.Materials,
    models.ReadingLog.name: models.ReadingLog,
    models.Notes.name: models.Notes,
    models.Cards.name: models.Cards,
    models.Repeats.name: models.Repeats,
    models.NoteRepeatsHistory.name: models.NoteRepeatsHistory,
}


def _fold_legacy_statuses(dump_data: DUMP_TYPE) -> DUMP_TYPE:
    if (statuses := dump_data.get(LEGACY_STATUSES_TABLE)) is None:
        return dump_data

    materials = dump_data.get(models.Materials.name, [])
    material_ids = {material["material_id"] for material in materials}
    if orphans := sum(status["material_id"] not in material_ids for status in statuses):
        logger.warning("%s legacy statuses reference missing materials, skipped", orphans)

    status_by_material = {status["material_id"]: status for status in statuses}
    folded_materials = [
        _fold_status(material, status_by_material.get(material["material_id"], {}))
        for material in materials
    ]

    return {
        **{
            table_name: rows
            for table_name, rows in dump_data.items()
            if table_name != LEGACY_STATUSES_TABLE
        },
        # JSON dumps carry nulls, DUMP_TYPE does not model them.
        models.Materials.name: folded_materials,  # type: ignore[dict-item]
    }


def _fold_status(
    material: dict[str, JSON_FIELD_TYPES],
    status: dict[str, JSON_FIELD_TYPES],
) -> dict[str, JSON_FIELD_TYPES | None]:
    return {
        **material,
        "started_at": status.get("started_at", material.get("started_at")),
        "completed_at": status.get("completed_at", material.get("completed_at")),
    }


def _date_columns(table: Table) -> dict[str, type[datetime.date]]:
    """Columns that the dump stores as date or datetime strings."""
    return {
        column.name: column.type.python_type
        for column in table.columns
        if isinstance(column.type, Date | DateTime)
    }


def _parse_date(
    value: JSON_FIELD_TYPES,
    python_type: type[datetime.date],
) -> JSON_FIELD_TYPES | DATE_TYPES:
    if not isinstance(value, str) or not value:
        return value
    if python_type is datetime.datetime:
        return datetime.datetime.strptime(value, settings.DATETIME_FORMAT)  # noqa: DTZ007
    return datetime.datetime.strptime(value, settings.DATE_FORMAT).date()  # noqa: DTZ007


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
        for shift in range(len(values) // 1000 + 1):
            objects = values[shift * 1000 : (shift + 1) * 1000]

            stmt = table.insert().values(objects)
            await conn.execute(stmt)

            logger.info("%s: %s rows inserted", table.name, len(objects))


async def get_tables_analytics() -> dict[str, int]:
    query = [
        f"SELECT '{table}_count' AS name, COUNT(1) AS cnt FROM {table}"  # noqa: S608
        for table in TABLES
    ]

    query_str = "\nUNION\n".join(query)
    stmt = sa.text(query_str)

    async with database.session() as ses:
        res = (await ses.execute(stmt)).all()

    return {r.name: r.cnt for r in res}


async def _set_seq_value(
    *,
    conn: AsyncSession,
    table_name: str,
    field_name: str,
    rows: TableSnapshot,
) -> None:
    # TODO: iterate over table and find Serial fields
    max_index = max(row.get(field_name, 0) for row in rows.rows)
    seq_name = f"{table_name}_{field_name}_seq"

    query = f"SELECT setval('{seq_name}', {max_index}, true)"
    await conn.execute(sa.text(query))


async def set_notes_seq_value(notes: TableSnapshot, conn: AsyncSession) -> None:
    model = models.Notes

    await _set_seq_value(
        conn=conn,
        table_name=model.name,
        field_name=model.c.note_number.name,
        rows=notes,
    )
