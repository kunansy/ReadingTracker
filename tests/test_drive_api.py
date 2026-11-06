import orjson
import pytest

from tracker.common import settings
from tracker.google_drive import drive_api
from tracker.protos import backup_pb2


def _info(fmt: int, backup_id: str = "id1") -> backup_pb2.BackupInfo:
    return backup_pb2.BackupInfo(id=backup_id, name=f"{backup_id}.file", format=fmt)


class FakeStub:
    def __init__(self, info: backup_pb2.BackupInfo, data: list[bytes]) -> None:
        self.info = info
        self.data = data
        self.restore_requests: list[backup_pb2.RestoreRequest] = []
        self.download_refs: list[backup_pb2.BackupRef] = []

    async def GetBackup(self, ref: backup_pb2.BackupRef) -> backup_pb2.BackupInfo:  # noqa: N802
        assert ref.latest
        return self.info

    async def Restore(self, req: backup_pb2.RestoreRequest) -> backup_pb2.RestoreReply:  # noqa: N802
        self.restore_requests.append(req)
        return backup_pb2.RestoreReply(
            restored=self.info,
            pre_restore_backup=_info(backup_pb2.BACKUP_FORMAT_PG_CUSTOM, "safety"),
        )

    async def DownloadBackup(self, ref: backup_pb2.BackupRef):  # noqa: N802
        self.download_refs.append(ref)
        yield backup_pb2.DownloadChunk(info=self.info)
        for chunk in self.data:
            yield backup_pb2.DownloadChunk(data=chunk)


async def test_download_joins_chunks():
    stub = FakeStub(_info(backup_pb2.BACKUP_FORMAT_PG_CUSTOM), [b"ab", b"cd"])

    info, content = await drive_api._download(stub, drive_api.LATEST)

    assert info.id == "id1"
    assert content == b"abcd"


async def test_download_requires_info_message():
    class NoInfoStub(FakeStub):
        async def DownloadBackup(self, ref):  # noqa: N802
            yield backup_pb2.DownloadChunk(data=b"x")

    stub = NoInfoStub(_info(backup_pb2.BACKUP_FORMAT_PG_CUSTOM), [])

    with pytest.raises(drive_api.GoogleDriveException):
        await drive_api._download(stub, drive_api.LATEST)


async def test_restore_pg_backup_uses_restore_rpc(mocker):
    engine = mocker.patch.object(drive_api.database, "engine")
    engine.dispose = mocker.AsyncMock()
    legacy = mocker.patch.object(drive_api, "_restore_legacy")
    stub = FakeStub(_info(backup_pb2.BACKUP_FORMAT_PG_CUSTOM), [])

    await drive_api._restore_from_service(stub)

    [req] = stub.restore_requests
    assert req.backup.id == "id1"
    assert req.confirm_db_name == settings.DB_NAME
    engine.dispose.assert_awaited_once()
    legacy.assert_not_called()
    assert not stub.download_refs


async def test_restore_legacy_backup_downloads_json(mocker):
    legacy = mocker.patch.object(drive_api, "_restore_legacy")
    dump = {"materials": [{"material_id": "x"}]}
    stub = FakeStub(
        _info(backup_pb2.BACKUP_FORMAT_LEGACY_JSON_ZSTD),
        [orjson.dumps(dump)[:5], orjson.dumps(dump)[5:]],
    )

    await drive_api._restore_from_service(stub)

    legacy.assert_awaited_once_with(dump)
    assert not stub.restore_requests
    assert stub.download_refs[0].id == "id1"


async def test_restore_unknown_format_fails(mocker):
    mocker.patch.object(drive_api, "_restore_legacy")
    stub = FakeStub(_info(backup_pb2.BACKUP_FORMAT_UNSPECIFIED), [])

    with pytest.raises(drive_api.GoogleDriveException):
        await drive_api._restore_from_service(stub)

    assert not stub.restore_requests
