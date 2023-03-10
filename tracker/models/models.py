import datetime

import sqlalchemy
import uuid6
from sqlalchemy import BigInteger, Boolean, Date, DateTime, Enum, Integer, MetaData, Table, Unicode, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql.type_api import UserDefinedType

from tracker.models import enums


def Column(*args, **kwargs) -> sqlalchemy.Column:
    """ Make columns not nullable by default """
    kwargs['nullable'] = kwargs.get('nullable', False)
    return sqlalchemy.Column(*args, **kwargs)


def ForeignKey(*args, **kwargs) -> sqlalchemy.ForeignKey:
    """ Make foreign keys onupdate = 'CASCADE'
    ondelete = 'RESTRICT' by default """
    kwargs['onupdate'] = kwargs.get('onupdate', 'CASCADE')
    kwargs['ondelete'] = kwargs.get('ondelete', 'RESTRICT')

    return sqlalchemy.ForeignKey(*args, **kwargs)


def PrimaryKey(*args, **kwargs) -> sqlalchemy.Column:
    if len(args) == 1:
        args = *args, UUID

    kwargs['default'] = kwargs.get('default', _uuid_gen)
    kwargs['primary_key'] = True

    return Column(*args, **kwargs)


class Serial(UserDefinedType):
    def get_col_spec(self, **kw):
        return "serial"


def _uuid_gen() -> str:
    return str(uuid6.uuid6())


_utc_now = datetime.datetime.utcnow
metadata = MetaData()

Materials = Table(
    'materials',
    metadata,

    PrimaryKey('material_id'),
    Column('title', Unicode(256)),
    Column('authors', Unicode(256)),
    Column('pages', Integer),
    Column('material_type', Enum(enums.MaterialTypesEnum), default=enums.MaterialTypesEnum.book),
    Column('tags', Unicode(256), nullable=True),
    Column('link', Unicode(2048), nullable=True),
    Column('added_at', DateTime, default=_utc_now),
    Column('is_outlined', Boolean, default=False),
    Column('index', Serial),

    UniqueConstraint('title', 'material_type', name='uix_material'),
    # uniqueness should be deferrable
    UniqueConstraint('index', name='uix_materials_index', deferrable=True),
)

ReadingLog = Table(
    'reading_log',
    metadata,

    PrimaryKey('log_id'),
    Column('material_id', ForeignKey('materials.material_id'), index=True),
    Column('count', Integer),
    Column('date', Date, default=_utc_now),

    UniqueConstraint('material_id', 'date', name='uix_reading_log')
)

Statuses = Table(
    'statuses',
    metadata,

    PrimaryKey('status_id'),
    Column('material_id', ForeignKey('materials.material_id'),
           unique=True, index=True),
    Column('started_at', DateTime),
    Column('completed_at', DateTime, nullable=True)
)

Notes = Table(
    'notes',
    metadata,

    PrimaryKey('note_id'),
    Column('note_number', Integer, autoincrement=True, unique=True),
    Column('material_id', ForeignKey('materials.material_id'), index=True),
    Column('link_id', ForeignKey('notes.note_id'), nullable=True, comment='By Zettelkasten method'),
    Column('content', Unicode(65_536)),
    Column('added_at', DateTime, default=_utc_now),
    Column('chapter', Integer),
    Column('page', Integer),
    Column('tags', JSONB, nullable=True),
    Column('is_deleted', Boolean, default=False)
)

Cards = Table(
    'cards',
    metadata,

    PrimaryKey('card_id'),
    Column('material_id', ForeignKey('materials.material_id'), index=True),
    Column('note_id', ForeignKey('notes.note_id'), index=True),
    Column('question', Unicode),
    Column('answer', Unicode, nullable=True),
    Column('added_at', DateTime, default=_utc_now),
)

Repeats = Table(
    'repeats',
    metadata,

    PrimaryKey('repeat_id'),
    Column('material_id', ForeignKey('materials.material_id'), index=True),
    Column('repeated_at', DateTime, default=_utc_now)
)

NoteRepeatsHistory = Table(
    'note_repeats_history',
    metadata,

    PrimaryKey('repeat_id'),
    Column('note_id', ForeignKey('notes.note_id'), index=True),
    Column('user_id', BigInteger, index=True, comment='Telegram user id'),
    Column('repeated_at', DateTime, default=_utc_now)
)
