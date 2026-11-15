import datetime
import inspect
from contextlib import asynccontextmanager
from pathlib import Path

import grpc
import pytest
from grpc.aio import AioRpcError, Metadata

from tracker.backup import client
from tracker.common import database, settings
from tracker.protos import backup_pb2, backup_pb2_grpc


PG_CUSTOM = backup_pb2.BACKUP_FORMAT_PG_CUSTOM
LEGACY_JSON = backup_pb2.BACKUP_FORMAT_LEGACY_JSON_ZSTD
UNSPECIFIED = backup_pb2.BACKUP_FORMAT_UNSPECIFIED
RPC_ERROR_MESSAGE = "Backup service error: UNAVAILABLE: service down"


def _info(fmt: int, backup_id: str = "id1") -> backup_pb2.BackupInfo:
    return backup_pb2.BackupInfo(id=backup_id, name=f"{backup_id}.file", format=fmt)


FROZEN_NOW = datetime.datetime(2024, 1, 2, 3, 4, 5, 678)  # noqa: DTZ001


def _frozen_clock() -> datetime.datetime:
    return FROZEN_NOW


def _rpc_error(code: grpc.StatusCode = grpc.StatusCode.UNAVAILABLE) -> AioRpcError:
    return AioRpcError(code, Metadata(), Metadata(), details="service down")


class UnavailableStub:
    def __init__(self) -> None:
        self.error = _rpc_error()

    async def Restore(self, req):  # noqa: N802
        raise self.error

    async def CreateBackup(self, req):  # noqa: N802
        raise self.error

    async def DownloadBackup(self, ref):  # noqa: N802
        raise self.error
        yield


class FakeStub:
    def __init__(self, info: backup_pb2.BackupInfo, data: list[bytes]) -> None:
        self.info = info
        self.data = data
        self.restore_requests: list[backup_pb2.RestoreRequest] = []
        self.download_refs: list[backup_pb2.BackupRef] = []
        self.create_requests: list[backup_pb2.CreateBackupRequest] = []

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

        mocker.patch.object(client, "_backup_stub", open_stub)
        return opened

    return install


@pytest.mark.parametrize(
    "code",
    [
        grpc.StatusCode.UNAVAILABLE,
        grpc.StatusCode.NOT_FOUND,
        grpc.StatusCode.FAILED_PRECONDITION,
    ],
)
async def test_rpc_error_becomes_a_backup_exception_with_its_code(code):
    error = _rpc_error(code)

    with pytest.raises(client.BackupException) as e:
        async with client._rpc_errors():
            raise error

    assert str(e.value) == f"Backup service error: {code.name}: service down"
    assert e.value.__cause__ is error


async def test_other_errors_pass_through_rpc_errors_unchanged():
    with pytest.raises(RuntimeError, match="boom"):
        async with client._rpc_errors():
            raise RuntimeError("boom")


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

        mocker.patch.object(client, "grpc_chan", open_channel)

        async with client._backup_stub() as stub:
            assert isinstance(stub, backup_pb2_grpc.BackupStub)
            assert closed == []

        assert targets == [settings.BACKUP_TARGET]
        assert settings.BACKUP_TARGET == "127.0.0.1:1"
        assert closed == [True]
        channel.unary_unary.assert_called()


class TestDownload:
    @pytest.mark.parametrize(
        ("chunks", "content"),
        [([b"ab", b"cd"], b"abcd"), ([b"only"], b"only"), ([], b""), ([b"", b"x", b""], b"x")],
        ids=["two-chunks", "one-chunk", "no-chunks", "empty-chunks"],
    )
    async def test_chunks_are_joined_in_order(self, chunks, content):
        stub = FakeStub(_info(PG_CUSTOM), chunks)

        info, downloaded = await client._download(stub, client.LATEST)

        assert info == _info(PG_CUSTOM)
        assert downloaded == content
        assert stub.download_refs == [client.LATEST]

    async def test_info_message_may_come_after_the_data(self):
        class InfoLastStub(FakeStub):
            async def DownloadBackup(self, ref):  # noqa: N802
                yield backup_pb2.DownloadChunk(data=b"x")
                yield backup_pb2.DownloadChunk(info=self.info)

        stub = InfoLastStub(_info(PG_CUSTOM), [])

        info, downloaded = await client._download(stub, client.LATEST)

        assert (info.id, downloaded) == ("id1", b"x")

    async def test_last_info_message_wins(self):
        class TwoInfosStub(FakeStub):
            async def DownloadBackup(self, ref):  # noqa: N802
                yield backup_pb2.DownloadChunk(info=_info(PG_CUSTOM, "first"))
                yield backup_pb2.DownloadChunk(info=_info(PG_CUSTOM, "second"))

        info, _ = await client._download(TwoInfosStub(_info(PG_CUSTOM), []), client.LATEST)

        assert info.id == "second"

    async def test_stream_without_info_message_raises(self):
        class NoInfoStub(FakeStub):
            async def DownloadBackup(self, ref):  # noqa: N802
                yield backup_pb2.DownloadChunk(data=b"x")

        stub = NoInfoStub(_info(PG_CUSTOM), [])

        with pytest.raises(client.BackupException) as e:
            await client._download(stub, client.LATEST)

        assert str(e.value) == "Backup stream has no info message"

    async def test_empty_stream_raises(self):
        class EmptyStub(FakeStub):
            async def DownloadBackup(self, ref):  # noqa: N802
                return
                yield

        with pytest.raises(client.BackupException):
            await client._download(EmptyStub(_info(PG_CUSTOM), []), client.LATEST)


class TestRestore:
    async def test_latest_backup_is_restored_by_the_service_and_the_pool_disposed(
        self,
        mocker,
        backup_stub,
    ):
        engine = mocker.patch.object(client.database, "engine")
        engine.dispose = mocker.AsyncMock()
        stub = FakeStub(_info(PG_CUSTOM), [])
        opened = backup_stub(stub)

        await client.restore()

        [req] = stub.restore_requests
        assert req.backup == client.LATEST
        assert req.confirm_db_name == settings.DB_NAME
        assert settings.DB_NAME == "tracker_unit"
        engine.dispose.assert_awaited_once_with()
        assert opened == [stub]
        assert not stub.download_refs

    async def test_service_failure_still_disposes_the_pool(self, mocker, backup_stub):
        engine = mocker.patch.object(client.database, "engine")
        engine.dispose = mocker.AsyncMock()
        stub = UnavailableStub()
        backup_stub(stub)

        with pytest.raises(client.BackupException) as e:
            await client.restore()

        assert str(e.value) == RPC_ERROR_MESSAGE
        assert e.value.__cause__ is stub.error
        engine.dispose.assert_awaited_once_with()

    async def test_unexpected_failure_propagates_and_disposes_the_pool(
        self,
        mocker,
        backup_stub,
    ):
        class FailingStub(FakeStub):
            async def Restore(self, req):  # noqa: N802
                raise RuntimeError("boom")

        engine = mocker.patch.object(client.database, "engine")
        engine.dispose = mocker.AsyncMock()
        backup_stub(FailingStub(_info(PG_CUSTOM), []))

        with pytest.raises(RuntimeError, match="boom"):
            await client.restore()

        engine.dispose.assert_awaited_once_with()


    async def test_dispose_failure_does_not_mask_the_service_failure(
        self,
        mocker,
        backup_stub,
    ):
        engine = mocker.patch.object(client.database, "engine")
        engine.dispose = mocker.AsyncMock(side_effect=RuntimeError("dispose failed"))
        backup_stub(UnavailableStub())
        log = mocker.patch.object(client.logger, "exception")

        with pytest.raises(client.BackupException) as e:
            await client.restore()

        assert str(e.value) == RPC_ERROR_MESSAGE
        log.assert_called_once_with("Engine dispose after restore failed")

    async def test_dispose_failure_after_a_restore_is_logged(self, mocker, backup_stub):
        engine = mocker.patch.object(client.database, "engine")
        engine.dispose = mocker.AsyncMock(side_effect=RuntimeError("dispose failed"))
        stub = FakeStub(_info(PG_CUSTOM), [])
        backup_stub(stub)
        log = mocker.patch.object(client.logger, "exception")

        await client.restore()

        assert len(stub.restore_requests) == 1
        log.assert_called_once_with("Engine dispose after restore failed")


class TestBackup:
    async def test_returns_the_id_of_the_created_backup(self, backup_stub):
        stub = FakeStub(_info(PG_CUSTOM, "created"), [])
        backup_stub(stub)

        backup_id = await client.backup()

        assert backup_id == "created"
        assert stub.create_requests == [backup_pb2.CreateBackupRequest()]

    async def test_service_failure_is_a_backup_exception(self, backup_stub):
        stub = UnavailableStub()
        backup_stub(stub)

        with pytest.raises(client.BackupException) as e:
            await client.backup()

        assert str(e.value) == RPC_ERROR_MESSAGE
        assert e.value.__cause__ is stub.error


class TestDownloadLatest:
    @pytest.fixture(autouse=True)
    def data_dir(self, mocker, tmp_path) -> Path:
        mocker.patch.object(settings, "DATA_DIR", tmp_path)
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

        filepath = await client.download_latest(clock=_frozen_clock)

        assert filepath == data_dir / f"last_dump_2024-01-02_03-04-05.{extension}"
        assert filepath.read_bytes() == b"content"
        assert stub.download_refs == [client.LATEST]

    async def test_custom_prefix(self, backup_stub, data_dir):
        backup_stub(FakeStub(_info(PG_CUSTOM), [b"x"]))

        filepath = await client.download_latest(prefix="manual", clock=_frozen_clock)

        assert filepath == data_dir / "manual_2024-01-02_03-04-05.pgdump"

    async def test_empty_backup_is_saved_as_empty_file(self, backup_stub):
        backup_stub(FakeStub(_info(PG_CUSTOM), []))

        filepath = await client.download_latest(clock=_frozen_clock)

        assert filepath.read_bytes() == b""

    async def test_unknown_format_raises_and_saves_nothing(self, backup_stub, data_dir):
        backup_stub(FakeStub(_info(UNSPECIFIED), [b"x"]))

        with pytest.raises(client.BackupException) as e:
            await client.download_latest(clock=_frozen_clock)

        assert str(e.value) == "Unsupported backup format of 'id1.file'"
        assert list(data_dir.iterdir()) == []

    async def test_service_failure_is_a_backup_exception_and_saves_nothing(
        self,
        backup_stub,
        data_dir,
    ):
        stub = UnavailableStub()
        backup_stub(stub)

        with pytest.raises(client.BackupException) as e:
            await client.download_latest(clock=_frozen_clock)

        assert str(e.value) == RPC_ERROR_MESSAGE
        assert e.value.__cause__ is stub.error
        assert list(data_dir.iterdir()) == []

    async def test_failure_mid_stream_is_a_backup_exception_and_saves_nothing(
        self,
        backup_stub,
        data_dir,
    ):
        error = _rpc_error(grpc.StatusCode.INTERNAL)

        class BrokenStreamStub(FakeStub):
            async def DownloadBackup(self, ref):  # noqa: N802
                yield backup_pb2.DownloadChunk(info=self.info)
                yield backup_pb2.DownloadChunk(data=b"x")
                raise error

        backup_stub(BrokenStreamStub(_info(PG_CUSTOM), []))

        with pytest.raises(client.BackupException) as e:
            await client.download_latest(clock=_frozen_clock)

        assert str(e.value) == "Backup service error: INTERNAL: service down"
        assert e.value.__cause__ is error
        assert list(data_dir.iterdir()) == []

    def test_default_clock_is_the_database_utc_clock(self):
        clock = inspect.signature(client.download_latest).parameters["clock"]

        assert clock.default is database.utcnow

    async def test_file_is_written_off_the_event_loop(self, mocker, backup_stub):
        backup_stub(FakeStub(_info(PG_CUSTOM), [b"x"]))
        to_thread = mocker.spy(client.asyncio, "to_thread")

        filepath = await client.download_latest(clock=_frozen_clock)

        to_thread.assert_awaited_once_with(filepath.write_bytes, b"x")


def test_dump_extensions_cover_both_backup_formats():
    assert client.DUMP_EXTENSIONS == {PG_CUSTOM: "pgdump", LEGACY_JSON: "json"}
    assert client.LATEST == backup_pb2.BackupRef(latest=True)


class TestGetDumpFilename:
    @pytest.mark.parametrize("prefix", ["last_dump", "", "дамп", "v1.2"])
    @pytest.mark.parametrize("extension", ["pgdump", "json"])
    def test_name_is_the_prefix_the_time_and_the_extension(self, prefix, extension):
        filename = client.get_dump_filename(
            prefix=prefix,
            extension=extension,
            now=FROZEN_NOW,
        )

        assert filename == settings.DATA_DIR / f"{prefix}_2024-01-02_03-04-05.{extension}"

