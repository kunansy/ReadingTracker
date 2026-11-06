import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class BackupFormat(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    BACKUP_FORMAT_UNSPECIFIED: _ClassVar[BackupFormat]
    BACKUP_FORMAT_PG_CUSTOM: _ClassVar[BackupFormat]
    BACKUP_FORMAT_LEGACY_JSON_ZSTD: _ClassVar[BackupFormat]

class BackupKind(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    BACKUP_KIND_UNSPECIFIED: _ClassVar[BackupKind]
    BACKUP_KIND_REGULAR: _ClassVar[BackupKind]
    BACKUP_KIND_PRE_RESTORE: _ClassVar[BackupKind]
BACKUP_FORMAT_UNSPECIFIED: BackupFormat
BACKUP_FORMAT_PG_CUSTOM: BackupFormat
BACKUP_FORMAT_LEGACY_JSON_ZSTD: BackupFormat
BACKUP_KIND_UNSPECIFIED: BackupKind
BACKUP_KIND_REGULAR: BackupKind
BACKUP_KIND_PRE_RESTORE: BackupKind

class BackupInfo(_message.Message):
    __slots__ = ("id", "name", "created_at", "size_bytes", "format", "kind")
    ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    SIZE_BYTES_FIELD_NUMBER: _ClassVar[int]
    FORMAT_FIELD_NUMBER: _ClassVar[int]
    KIND_FIELD_NUMBER: _ClassVar[int]
    id: str
    name: str
    created_at: _timestamp_pb2.Timestamp
    size_bytes: int
    format: BackupFormat
    kind: BackupKind
    def __init__(self, id: _Optional[str] = ..., name: _Optional[str] = ..., created_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., size_bytes: _Optional[int] = ..., format: _Optional[_Union[BackupFormat, str]] = ..., kind: _Optional[_Union[BackupKind, str]] = ...) -> None: ...

class CreateBackupRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ListBackupsRequest(_message.Message):
    __slots__ = ("page_size", "page_token")
    PAGE_SIZE_FIELD_NUMBER: _ClassVar[int]
    PAGE_TOKEN_FIELD_NUMBER: _ClassVar[int]
    page_size: int
    page_token: str
    def __init__(self, page_size: _Optional[int] = ..., page_token: _Optional[str] = ...) -> None: ...

class ListBackupsReply(_message.Message):
    __slots__ = ("backups", "next_page_token")
    BACKUPS_FIELD_NUMBER: _ClassVar[int]
    NEXT_PAGE_TOKEN_FIELD_NUMBER: _ClassVar[int]
    backups: _containers.RepeatedCompositeFieldContainer[BackupInfo]
    next_page_token: str
    def __init__(self, backups: _Optional[_Iterable[_Union[BackupInfo, _Mapping]]] = ..., next_page_token: _Optional[str] = ...) -> None: ...

class BackupRef(_message.Message):
    __slots__ = ("id", "latest")
    ID_FIELD_NUMBER: _ClassVar[int]
    LATEST_FIELD_NUMBER: _ClassVar[int]
    id: str
    latest: bool
    def __init__(self, id: _Optional[str] = ..., latest: bool = ...) -> None: ...

class DownloadChunk(_message.Message):
    __slots__ = ("info", "data")
    INFO_FIELD_NUMBER: _ClassVar[int]
    DATA_FIELD_NUMBER: _ClassVar[int]
    info: BackupInfo
    data: bytes
    def __init__(self, info: _Optional[_Union[BackupInfo, _Mapping]] = ..., data: _Optional[bytes] = ...) -> None: ...

class RestoreRequest(_message.Message):
    __slots__ = ("backup", "confirm_db_name")
    BACKUP_FIELD_NUMBER: _ClassVar[int]
    CONFIRM_DB_NAME_FIELD_NUMBER: _ClassVar[int]
    backup: BackupRef
    confirm_db_name: str
    def __init__(self, backup: _Optional[_Union[BackupRef, _Mapping]] = ..., confirm_db_name: _Optional[str] = ...) -> None: ...

class RestoreReply(_message.Message):
    __slots__ = ("restored", "pre_restore_backup")
    RESTORED_FIELD_NUMBER: _ClassVar[int]
    PRE_RESTORE_BACKUP_FIELD_NUMBER: _ClassVar[int]
    restored: BackupInfo
    pre_restore_backup: BackupInfo
    def __init__(self, restored: _Optional[_Union[BackupInfo, _Mapping]] = ..., pre_restore_backup: _Optional[_Union[BackupInfo, _Mapping]] = ...) -> None: ...

class HealthcheckRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class HealthcheckReply(_message.Message):
    __slots__ = ("is_ok",)
    IS_OK_FIELD_NUMBER: _ClassVar[int]
    is_ok: bool
    def __init__(self, is_ok: bool = ...) -> None: ...
