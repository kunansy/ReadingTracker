import datetime
import uuid

import sqlalchemy
from sqlalchemy import Date, Integer, MetaData, Table, Unicode
from sqlalchemy.dialects.postgresql import UUID


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

Material = Table(
    'material',
    metadata,

    PrimaryKey('material_id', Integer),
    Column('title', Unicode(256)),
    Column('authors ', Unicode(256)),
    Column('pages', Integer),
    Column('tags', Unicode(256), nullable=True)
)

ReadingLog = Table(
    'reading_log',
    metadata,

    PrimaryKey('log_id'),
    Column('material_id', ForeignKey('material.material_id'), index=True),
    Column('count', Integer),
    Column('date', Date, default=_utc_now)
)

Status = Table(
    'status',
    metadata,

    PrimaryKey('status_id', Integer),
    Column('material_id', ForeignKey('material.material_id'),
           unique=True, index=True),
    Column('begin', Date),
    Column('end', Date)
)

Note = Table(
    'note',
    metadata,

    PrimaryKey('id', Integer),
    Column('content', Unicode(65_536)),
    Column('material_id', ForeignKey('material.material_id'), index=True),
    Column('date', Date),
    Column('chapter', Integer),
    Column('page', Integer)
)

Card = Table(
    'card',
    metadata,

    PrimaryKey('card_id', Integer),
    Column('question', Unicode),
    Column('answer', Unicode, nullable=True),
    Column('date', Date),
    Column('material_id', ForeignKey('material.material_id'), index=True),
    Column('note_id', ForeignKey('note.id'), index=True)
)
