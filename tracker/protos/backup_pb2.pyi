from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class BackupRequest(_message.Message):
    __slots__ = ["db_host", "db_port", "db_username", "db_password", "db_name", "with_enc"]
    DB_HOST_FIELD_NUMBER: _ClassVar[int]
    DB_PORT_FIELD_NUMBER: _ClassVar[int]
    DB_USERNAME_FIELD_NUMBER: _ClassVar[int]
    DB_PASSWORD_FIELD_NUMBER: _ClassVar[int]
    DB_NAME_FIELD_NUMBER: _ClassVar[int]
    WITH_ENC_FIELD_NUMBER: _ClassVar[int]
    db_host: str
    db_port: str
    db_username: str
    db_password: str
    db_name: str
    with_enc: bool
    def __init__(self,
                 db_host: _Optional[str] = ...,
                 db_port: _Optional[str] = ...,
                 db_username: _Optional[str] = ...,
                 db_password: _Optional[str] = ...,
                 db_name: _Optional[str] = ...,
                 with_enc: bool = ...) -> None: ...

class BackupReply(_message.Message):
    __slots__ = ["file_id"]
    FILE_ID_FIELD_NUMBER: _ClassVar[int]
    file_id: str
    def __init__(self, file_id: _Optional[str] = ...) -> None: ...
