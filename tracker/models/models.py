import datetime
import uuid

import sqlalchemy
from sqlalchemy import Date, DateTime, Integer, MetaData, Table, Unicode, Boolean, Enum, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

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


def _uuid_gen():
    return str(uuid.uuid4())


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

    UniqueConstraint('title', 'material_type', name='uix_material')
)

ReadingLog = Table(
    'reading_log',
    metadata,

    PrimaryKey('log_id'),
    Column('material_id', ForeignKey('materials.material_id'), index=True),
    Column('count', Integer),
    Column('date', Date, default=_utc_now, unique=True),

    UniqueConstraint('material_id', 'date', name='uix_reading_log')
)

Statuses = Table(
    'statuses',
    metadata,

    PrimaryKey('status_id'),
    Column('material_id', ForeignKey('materials.material_id'),
           unique=True, index=True),
    Column('started_at', Date),
    Column('completed_at', Date, nullable=True)
)

Notes = Table(
    'notes',
    metadata,

    PrimaryKey('note_id'),
    Column('material_id', ForeignKey('materials.material_id'), index=True),
    Column('content', Unicode(65_536)),
    Column('added_at', DateTime, default=_utc_now),
    Column('chapter', Integer),
    Column('page', Integer),
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
    Column('material_id', ForeignKey('materials.material_id'), index=True, unique=True),
    Column('repeated_at', DateTime, default=_utc_now)
)
