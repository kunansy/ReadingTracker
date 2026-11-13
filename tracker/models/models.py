import datetime
from typing import Final

import sqlalchemy
import uuid6
from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Index,
    Integer,
    MetaData,
    Table,
    Unicode,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql.type_api import UserDefinedType

from tracker.models import enums


MAX_CHAPTER_LENGTH: Final[int] = 256


def Column(*args, **kwargs) -> sqlalchemy.Column:
    """Make columns not nullable by default."""
    kwargs["nullable"] = kwargs.get("nullable", False)
    return sqlalchemy.Column(*args, **kwargs)


def PrimaryKey(*args, **kwargs) -> sqlalchemy.Column:
    if len(args) == 1:
        args = *args, UUID

    kwargs["default"] = kwargs.get("default", generate_id)
    kwargs["primary_key"] = True

    return Column(*args, **kwargs)


class Serial(UserDefinedType):
    """Sqlalchemy have no postgres Serial type."""

    cache_ok = True

    def get_col_spec(self, **kw) -> str:  # noqa: ARG002
        return "serial"


def generate_id() -> str:
    return str(uuid6.uuid7())


def SortKey() -> sqlalchemy.Column:
    return Column("sort_key", Unicode(512, collation="C"), nullable=False, unique=True)


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)


metadata = MetaData()

Materials = Table(
    "materials",
    metadata,
    PrimaryKey("material_id"),
    Column("title", Unicode(256)),
    Column("authors", Unicode(256)),
    Column("pages", Integer),
    Column(
        "material_type",
        Unicode(50),
        default=enums.MaterialTypesEnum.book,
    ),
    Column("tags", Unicode(256), nullable=True),
    Column("link", Unicode(2048), nullable=True),
    Column("added_at", DateTime, default=_utc_now),
    Column("is_outlined", Boolean, default=False),
    Column("started_at", DateTime, nullable=True),
    Column("completed_at", DateTime, nullable=True),
    SortKey(),
    UniqueConstraint("title", "material_type", name="uix_material"),
    Index(
        "ix_materials_completed_at_sort_key",
        "completed_at",
        "sort_key",
        postgresql_where=sqlalchemy.text("completed_at IS NOT NULL"),
    ),
    Index(
        "ix_materials_started_at_sort_key",
        "started_at",
        "sort_key",
        postgresql_where=sqlalchemy.text("started_at IS NOT NULL"),
    ),
)

MATERIAL_IS_QUEUED: Final = Materials.c.started_at.is_(None)
MATERIAL_IS_STARTED: Final = Materials.c.started_at.is_not(None)
MATERIAL_IS_COMPLETED: Final = Materials.c.completed_at.is_not(None)
MATERIAL_IS_READING: Final = sqlalchemy.and_(
    MATERIAL_IS_STARTED,
    sqlalchemy.not_(MATERIAL_IS_COMPLETED),
)

ReadingLog = Table(
    "reading_log",
    metadata,
    PrimaryKey("log_id"),
    Column("material_id", UUID, index=True),
    Column("count", Integer),
    Column("date", Date, default=_utc_now),
    SortKey(),
    UniqueConstraint("material_id", "date", name="uix_reading_log"),
    Index("ix_reading_log_date_sort_key", "date", "sort_key"),
)

Notes = Table(
    "notes",
    metadata,
    PrimaryKey("note_id"),
    Column("note_number", Serial),
    Column("material_id", UUID, index=True),
    Column(
        "link_id",
        UUID,
        nullable=True,
        comment="By Zettelkasten method",
    ),
    Column("title", Unicode(4096), nullable=True, unique=True),
    Column("content", Unicode(65_536)),
    Column("added_at", DateTime, default=_utc_now),
    Column("chapter", Unicode(MAX_CHAPTER_LENGTH)),
    Column("page", Integer),
    Column("tags", JSONB, nullable=True),
    Column("is_deleted", Boolean, default=False),
    SortKey(),
    UniqueConstraint("note_number", name="uix_notes_note_number", deferrable=True),
    Index("ix_notes_link_id_note_number_sort_key", "link_id", "note_number", "sort_key"),
)

Cards = Table(
    "cards",
    metadata,
    PrimaryKey("card_id"),
    Column("material_id", UUID, index=True),
    Column("note_id", UUID, index=True),
    Column("question", Unicode),
    Column("answer", Unicode, nullable=True),
    Column("added_at", DateTime, default=_utc_now),
    SortKey(),
)

Repeats = Table(
    "repeats",
    metadata,
    PrimaryKey("repeat_id"),
    Column("material_id", UUID, index=True),
    Column("repeated_at", DateTime, default=_utc_now),
)

NoteRepeatsHistory = Table(
    "note_repeats_history",
    metadata,
    PrimaryKey("repeat_id"),
    Column("note_id", UUID, index=True),
    Column("user_id", BigInteger, comment="Telegram user id"),
    Column("repeated_at", DateTime, default=_utc_now),
)
