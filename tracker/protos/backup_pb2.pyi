from typing import ClassVar as _ClassVar

from google.protobuf import (
    descriptor as _descriptor,
    message as _message,
)


DESCRIPTOR: _descriptor.FileDescriptor


class DBRequest(_message.Message):
    __slots__ = ["db_host", "db_port", "db_username", "db_password", "db_name"]
    DB_HOST_FIELD_NUMBER: _ClassVar[int]
    DB_PORT_FIELD_NUMBER: _ClassVar[int]
    DB_USERNAME_FIELD_NUMBER: _ClassVar[int]
    DB_PASSWORD_FIELD_NUMBER: _ClassVar[int]
    DB_NAME_FIELD_NUMBER: _ClassVar[int]
    db_host: str
    db_port: int
    db_username: str
    db_password: str
    db_name: str
    def __init__(
        self,
        db_host: str | None = ...,
        db_port: int | None = ...,
        db_username: str | None = ...,
        db_password: str | None = ...,
        db_name: str | None = ...,
    ) -> None: ...

class BackupReply(_message.Message):
    __slots__ = ["file_id"]
    FILE_ID_FIELD_NUMBER: _ClassVar[int]
    file_id: str
    def __init__(self, file_id: str | None = ...) -> None: ...

class DownloadReply(_message.Message):
    __slots__ = ["file_content"]
    FILE_CONTENT_FIELD_NUMBER: _ClassVar[int]
    file_content: bytes
    def __init__(self, file_content: bytes | None = ...) -> None: ...


class HealthcheckReply(_message.Message):
    __slots__ = ["is_ok"]
    IS_OK_FIELD_NUMBER: _ClassVar[int]
    is_ok: bool
    def __init__(self, is_ok: bool = ...) -> None: ...


class Empty(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...
