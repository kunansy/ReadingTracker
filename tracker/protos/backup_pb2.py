# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: backup.proto
"""Generated protocol buffer code."""

from google.protobuf import (
    descriptor as _descriptor,
    descriptor_pool as _descriptor_pool,
    symbol_database as _symbol_database,
)
from google.protobuf.internal import builder as _builder


# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()

DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(
    b'\n\x0c\x62\x61\x63kup.proto\x12\x06\x62\x61\x63kup"h\n\tDBRequest\x12\x0f\n\x07\x64\x62_host\x18\x01 \x01(\t\x12\x0f\n\x07\x64\x62_port\x18\x02 \x01(\r\x12\x13\n\x0b\x64\x62_username\x18\x03 \x01(\t\x12\x13\n\x0b\x64\x62_password\x18\x04 \x01(\t\x12\x0f\n\x07\x64\x62_name\x18\x05 \x01(\t"\x1e\n\x0b\x42\x61\x63kupReply\x12\x0f\n\x07\x66ile_id\x18\x01 \x01(\t"%\n\rDownloadReply\x12\x14\n\x0c\x66ile_content\x18\x01 \x01(\x0c"!\n\x10HealthcheckReply\x12\r\n\x05is_ok\x18\x01 \x01(\x08"\x07\n\x05\x45mpty2\xb9\x01\n\x0bGoogleDrive\x12\x30\n\x06\x42\x61\x63kup\x12\x11.backup.DBRequest\x1a\x13.backup.BackupReply\x12<\n\x14\x44ownloadLatestBackup\x12\r.backup.Empty\x1a\x15.backup.DownloadReply\x12:\n\x0bHealthcheck\x12\x11.backup.DBRequest\x1a\x18.backup.HealthcheckReplyb\x06proto3',  # noqa: E501
)

_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, "backup_pb2", _globals)

if not _descriptor._USE_C_DESCRIPTORS:
    DESCRIPTOR._options = None

    _globals["_DBREQUEST"]._serialized_start = 24
    _globals["_DBREQUEST"]._serialized_end = 128
    _globals["_BACKUPREPLY"]._serialized_start = 130
    _globals["_BACKUPREPLY"]._serialized_end = 160
    _globals["_DOWNLOADREPLY"]._serialized_start = 162
    _globals["_DOWNLOADREPLY"]._serialized_end = 199
    _globals["_HEALTHCHECKREPLY"]._serialized_start = 201
    _globals["_HEALTHCHECKREPLY"]._serialized_end = 234
    _globals["_EMPTY"]._serialized_start = 236
    _globals["_EMPTY"]._serialized_end = 243
    _globals["_GOOGLEDRIVE"]._serialized_start = 246
    _globals["_GOOGLEDRIVE"]._serialized_end = 431
    # @@protoc_insertion_point(module_scope)
