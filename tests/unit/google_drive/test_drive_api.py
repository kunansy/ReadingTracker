import datetime
from contextlib import asynccontextmanager
from pathlib import Path

import orjson
import pytest

from tracker.common import database, settings
from tracker.google_drive import drive_api
from tracker.google_drive.db import DBSnapshot
from tracker.protos import backup_pb2, backup_pb2_grpc


PG_CUSTOM = backup_pb2.BACKUP_FORMAT_PG_CUSTOM
LEGACY_JSON = backup_pb2.BACKUP_FORMAT_LEGACY_JSON_ZSTD
UNSPECIFIED = backup_pb2.BACKUP_FORMAT_UNSPECIFIED


def _info(fmt: int, backup_id: str = "id1") -> backup_pb2.BackupInfo:
    return backup_pb2.BackupInfo(id=backup_id, name=f"{backup_id}.file", format=fmt)


class FakeStub:
    def __init__(self, info: backup_pb2.BackupInfo, data: list[bytes]) -> None:
        self.info = info
        self.data = data
        self.restore_requests: list[backup_pb2.RestoreRequest] = []
        self.download_refs: list[backup_pb2.BackupRef] = []
        self.create_requests: list[backup_pb2.CreateBackupRequest] = []

    async def GetBackup(self, ref: backup_pb2.BackupRef) -> backup_pb2.BackupInfo:  # noqa: N802
        assert ref.latest
        return self.info

    async def Restore(self, req: backup_pb2.RestoreRequest) -> backup_pb2.RestoreReply:  # noqa: N802
        self.restore_requests.append(req)
        return backup_pb2.RestoreReply(
            restored=self.info,
            pre_restore_backup=_info(PG_CUSTOM, "safety"),
        )

    async def DownloadBackup(self, ref: backup_pb2.BackupRef):  # noqa: N802
        self.download_refs.append(ref)
        yield backup_pb2.DownloadChunk(info=self.info)
        for chunk in self.data:
            yield backup_pb2.DownloadChunk(data=chunk)

    async def CreateBackup(  # noqa: N802
        self,
        req: backup_pb2.CreateBackupRequest,
    ) -> backup_pb2.BackupInfo:
        self.create_requests.append(req)
        return self.info


@pytest.fixture
def backup_stub(mocker):
    """Replace the gRPC channel with a fake stub and count how often it is opened."""

    def install(stub: FakeStub) -> list[FakeStub]:
        opened: list[FakeStub] = []

        @asynccontextmanager
        async def open_stub():
            opened.append(stub)
            yield stub

        mocker.patch.object(drive_api, "_backup_stub", open_stub)
        return opened

    return install


class TestBackupStub:
    async def test_stub_is_bound_to_a_channel_to_the_backup_service(self, mocker):
        channel = mocker.MagicMock()
        targets: list[str] = []
        closed: list[bool] = []

        @asynccontextmanager
        async def open_channel(target: str):
            targets.append(target)
            yield channel
            closed.append(True)

        mocker.patch.object(drive_api, "grpc_chan", open_channel)

        async with drive_api._backup_stub() as stub:
            assert isinstance(stub, backup_pb2_grpc.BackupStub)
            assert closed == []

        assert targets == [settings.BACKUP_TARGET]
        assert settings.BACKUP_TARGET == "127.0.0.1:1"
        assert closed == [True]
        channel.unary_unary.assert_called()


class TestReadLocalDump:
    def test_missing_file_raises(self, tmp_path):
        filepath = tmp_path / "absent.json"

        with pytest.raises(drive_api.GoogleDriveException) as e:
            drive_api._read_local_dump(filepath)

        assert str(e.value) == f"{filepath} file not found"

    def test_dump_is_parsed_as_json(self, tmp_path):
        filepath = tmp_path / "dump.json"
        filepath.write_text('{"materials": [{"title": "Заголовок"}], "notes": []}')

        assert drive_api._read_local_dump(filepath) == {
            "materials": [{"title": "Заголовок"}],
            "notes": [],
        }

    def test_invalid_json_raises(self, tmp_path):
        filepath = tmp_path / "dump.json"
        filepath.write_text("{not json")

        with pytest.raises(orjson.JSONDecodeError):
            drive_api._read_local_dump(filepath)


class TestDownload:
    @pytest.mark.parametrize(
        ("chunks", "content"),
        [([b"ab", b"cd"], b"abcd"), ([b"only"], b"only"), ([], b""), ([b"", b"x", b""], b"x")],
        ids=["two-chunks", "one-chunk", "no-chunks", "empty-chunks"],
    )
    async def test_chunks_are_joined_in_order(self, chunks, content):
        stub = FakeStub(_info(PG_CUSTOM), chunks)

        info, downloaded = await drive_api._download(stub, drive_api.LATEST)

        assert info == _info(PG_CUSTOM)
        assert downloaded == content
        assert stub.download_refs == [drive_api.LATEST]

    async def test_info_message_may_come_after_the_data(self):
        class InfoLastStub(FakeStub):
            async def DownloadBackup(self, ref):  # noqa: N802
                yield backup_pb2.DownloadChunk(data=b"x")
                yield backup_pb2.DownloadChunk(info=self.info)

        stub = InfoLastStub(_info(PG_CUSTOM), [])

        info, downloaded = await drive_api._download(stub, drive_api.LATEST)

        assert (info.id, downloaded) == ("id1", b"x")

    async def test_last_info_message_wins(self):
        class TwoInfosStub(FakeStub):
            async def DownloadBackup(self, ref):  # noqa: N802
                yield backup_pb2.DownloadChunk(info=_info(PG_CUSTOM, "first"))
                yield backup_pb2.DownloadChunk(info=_info(PG_CUSTOM, "second"))

        info, _ = await drive_api._download(TwoInfosStub(_info(PG_CUSTOM), []), drive_api.LATEST)

        assert info.id == "second"

    async def test_stream_without_info_message_raises(self):
        class NoInfoStub(FakeStub):
            async def DownloadBackup(self, ref):  # noqa: N802
                yield backup_pb2.DownloadChunk(data=b"x")

        stub = NoInfoStub(_info(PG_CUSTOM), [])

        with pytest.raises(drive_api.GoogleDriveException) as e:
            await drive_api._download(stub, drive_api.LATEST)

        assert str(e.value) == "Backup stream has no info message"

    async def test_empty_stream_raises(self):
        class EmptyStub(FakeStub):
            async def DownloadBackup(self, ref):  # noqa: N802
                return
                yield

        with pytest.raises(drive_api.GoogleDriveException):
            await drive_api._download(EmptyStub(_info(PG_CUSTOM), []), drive_api.LATEST)


class TestRestoreFromService:
    async def test_pg_backup_uses_restore_rpc_and_disposes_the_pool(self, mocker):
        engine = mocker.patch.object(drive_api.database, "engine")
        engine.dispose = mocker.AsyncMock()
        legacy = mocker.patch.object(drive_api, "_restore_legacy")
        stub = FakeStub(_info(PG_CUSTOM), [])

        await drive_api._restore_from_service(stub)

        [req] = stub.restore_requests
        assert req.backup.id == "id1"
        assert req.confirm_db_name == settings.DB_NAME
        assert settings.DB_NAME == "tracker_unit"
        engine.dispose.assert_awaited_once_with()
        legacy.assert_not_called()
        assert not stub.download_refs

    async def test_legacy_backup_is_downloaded_and_restored_from_json(self, mocker):
        legacy = mocker.patch.object(drive_api, "_restore_legacy")
        engine = mocker.patch.object(drive_api.database, "engine")
        engine.dispose = mocker.AsyncMock()
        dump = {"materials": [{"material_id": "x"}]}
        stub = FakeStub(_info(LEGACY_JSON), [orjson.dumps(dump)[:5], orjson.dumps(dump)[5:]])

        await drive_api._restore_from_service(stub)

        legacy.assert_awaited_once_with(dump)
        assert not stub.restore_requests
        assert [ref.id for ref in stub.download_refs] == ["id1"]
        engine.dispose.assert_not_awaited()

    async def test_unknown_format_fails_without_touching_the_database(self, mocker):
        legacy = mocker.patch.object(drive_api, "_restore_legacy")
        stub = FakeStub(_info(UNSPECIFIED), [])

        with pytest.raises(drive_api.GoogleDriveException) as e:
            await drive_api._restore_from_service(stub)

        assert str(e.value) == "Unsupported backup format of 'id1.file'"
        assert not stub.restore_requests
        assert not stub.download_refs
        legacy.assert_not_called()


class TestRestoreLegacy:
    @pytest.fixture
    def calls(self, mocker):
        ses = mocker.sentinel.session
        calls = mocker.Mock()

        @asynccontextmanager
        async def transaction():
            calls.begin()
            yield ses
            calls.commit()

        mocker.patch.object(drive_api.database, "transaction", transaction)
        for owner, name in [
            (drive_api.database, "recreate_db"),
            (drive_api.db, "restore_db"),
            (drive_api.db, "set_notes_seq_value"),
            (drive_api.database, "create_repeat_notes_matview"),
        ]:
            calls.attach_mock(mocker.patch.object(owner, name, mocker.AsyncMock()), name)
        return calls

    async def test_recreates_db_restores_snapshot_sets_notes_seq_and_creates_matview(
        self,
        mocker,
        calls,
    ):
        ses = mocker.sentinel.session
        dump = {
            "materials": [{"material_id": "m1", "title": "t"}],
            "notes": [{"note_id": "n1", "note_number": 7}],
        }
        snapshot = DBSnapshot.from_dump(dump)

        await drive_api._restore_legacy(dump)

        assert calls.mock_calls == [
            mocker.call.begin(),
            mocker.call.recreate_db(),
            mocker.call.restore_db(conn=ses, snapshot=snapshot),
            mocker.call.set_notes_seq_value(snapshot.to_dict()["notes"], ses),
            mocker.call.create_repeat_notes_matview(ses),
            mocker.call.commit(),
        ]

    @pytest.mark.xfail(
        strict=True,
        raises=KeyError,
        reason=(
            "BUG: tracker/google_drive/drive_api.py:68 snapshot_dict['notes'] raises "
            "KeyError when the dump has no notes table"
        ),
    )
    async def test_dump_without_notes_table_is_restored(self, mocker, calls):
        await drive_api._restore_legacy({"materials": [{"material_id": "m1"}]})

        calls.create_repeat_notes_matview.assert_awaited_once_with(mocker.sentinel.session)

    async def test_failed_restore_does_not_commit(self, mocker, calls):
        calls.restore_db.side_effect = ValueError("Snapshot is empty")

        with pytest.raises(ValueError, match="Snapshot is empty"):
            await drive_api._restore_legacy({})

        assert calls.mock_calls == [
            mocker.call.begin(),
            mocker.call.recreate_db(),
            mocker.call.restore_db(conn=mocker.sentinel.session, snapshot=DBSnapshot(tables=[])),
        ]


class TestRestore:
    async def test_without_dump_path_restores_from_the_service(self, mocker, backup_stub):
        stub = FakeStub(_info(PG_CUSTOM), [])
        opened = backup_stub(stub)
        from_service = mocker.patch.object(drive_api, "_restore_from_service")
        legacy = mocker.patch.object(drive_api, "_restore_legacy")

        await drive_api.restore()

        from_service.assert_awaited_once_with(stub)
        legacy.assert_not_called()
        assert opened == [stub]

    async def test_with_dump_path_restores_the_local_file(self, mocker, backup_stub, tmp_path):
        opened = backup_stub(FakeStub(_info(PG_CUSTOM), []))
        from_service = mocker.patch.object(drive_api, "_restore_from_service")
        legacy = mocker.patch.object(drive_api, "_restore_legacy")
        dump_path = tmp_path / "dump.json"
        dump_path.write_text('{"notes": [{"note_number": 1}]}')

        await drive_api.restore(dump_path=dump_path)

        legacy.assert_awaited_once_with({"notes": [{"note_number": 1}]})
        from_service.assert_not_called()
        assert opened == []

    async def test_missing_dump_file_raises(self, mocker, tmp_path):
        legacy = mocker.patch.object(drive_api, "_restore_legacy")

        with pytest.raises(drive_api.GoogleDriveException, match="file not found"):
            await drive_api.restore(dump_path=tmp_path / "absent.json")

        legacy.assert_not_called()


class TestBackup:
    async def test_returns_the_id_of_the_created_backup(self, backup_stub):
        stub = FakeStub(_info(PG_CUSTOM, "created"), [])
        backup_stub(stub)

        backup_id = await drive_api.backup()

        assert backup_id == "created"
        assert stub.create_requests == [backup_pb2.CreateBackupRequest()]


class TestDownloadLatest:
    @pytest.fixture(autouse=True)
    def data_dir(self, mocker, tmp_path) -> Path:
        mocker.patch.object(settings, "DATA_DIR", tmp_path)
        mocker.patch.object(
            database,
            "utcnow",
            return_value=datetime.datetime(2024, 1, 2, 3, 4, 5),  # noqa: DTZ001
        )
        return tmp_path

    @pytest.mark.parametrize(
        ("fmt", "extension"),
        [(PG_CUSTOM, "pgdump"), (LEGACY_JSON, "json")],
        ids=["pg-custom", "legacy-json"],
    )
    async def test_latest_backup_is_saved_with_the_format_extension(
        self,
        backup_stub,
        data_dir,
        fmt,
        extension,
    ):
        stub = FakeStub(_info(fmt), [b"con", b"tent"])
        backup_stub(stub)

        filepath = await drive_api.download_latest()

        assert filepath == data_dir / f"last_dump_2024-01-02_03-04-05.{extension}"
        assert filepath.read_bytes() == b"content"
        assert stub.download_refs == [drive_api.LATEST]

    async def test_custom_prefix(self, backup_stub, data_dir):
        backup_stub(FakeStub(_info(PG_CUSTOM), [b"x"]))

        filepath = await drive_api.download_latest(prefix="manual")

        assert filepath == data_dir / "manual_2024-01-02_03-04-05.pgdump"

    async def test_empty_backup_is_saved_as_empty_file(self, backup_stub):
        backup_stub(FakeStub(_info(PG_CUSTOM), []))

        filepath = await drive_api.download_latest()

        assert filepath.read_bytes() == b""

    async def test_unknown_format_raises_and_saves_nothing(self, backup_stub, data_dir):
        backup_stub(FakeStub(_info(UNSPECIFIED), [b"x"]))

        with pytest.raises(drive_api.GoogleDriveException) as e:
            await drive_api.download_latest()

        assert str(e.value) == "Unsupported backup format of 'id1.file'"
        assert list(data_dir.iterdir()) == []


def test_dump_extensions_cover_both_backup_formats():
    assert drive_api.DUMP_EXTENSIONS == {PG_CUSTOM: "pgdump", LEGACY_JSON: "json"}
    assert drive_api.LATEST == backup_pb2.BackupRef(latest=True)
