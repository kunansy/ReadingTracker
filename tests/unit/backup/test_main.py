import sys

import pytest

from tracker.backup import client, main


ACTIONS = ["backup", "restore", "download_latest"]


@pytest.fixture
def api(mocker):
    return {
        name: mocker.patch.object(client, name, mocker.AsyncMock())
        for name in ACTIONS
    }


@pytest.fixture
def argv(mocker):
    def install(*args: str) -> None:
        mocker.patch.object(sys, "argv", ["main.py", *args])

    return install


def _awaited(api) -> list[str]:
    return [name for name, mock in api.items() if mock.await_count]


class TestParseArgs:
    def test_no_flag_exits(self, argv):
        argv()

        with pytest.raises(SystemExit) as e:
            main.parse_args()

        assert e.value.code == 2

    @pytest.mark.parametrize(
        ("flag", "dest"),
        [
            ("--backup", "backup"),
            ("--restore", "restore"),
            ("--get-last-dump", "get_last_dump"),
        ],
    )
    def test_boolean_flag_sets_only_its_destination(self, argv, flag, dest):
        argv(flag)

        args = vars(main.parse_args())

        assert args.pop(dest) is True
        assert set(args.values()) == {False}

    def test_unknown_flag_exits(self, argv):
        argv("--unknown")

        with pytest.raises(SystemExit) as e:
            main.parse_args()

        assert e.value.code == 2


class TestMain:
    async def test_backup(self, argv, api):
        argv("--backup")

        await main.main()

        api["backup"].assert_awaited_once_with()
        assert _awaited(api) == ["backup"]

    async def test_restore(self, argv, api):
        argv("--restore")

        await main.main()

        api["restore"].assert_awaited_once_with()
        assert _awaited(api) == ["restore"]

    async def test_get_last_dump(self, argv, api):
        argv("--get-last-dump")

        await main.main()

        api["download_latest"].assert_awaited_once_with()
        assert _awaited(api) == ["download_latest"]

    async def test_no_flag_exits_and_runs_nothing(self, argv, api):
        argv()

        with pytest.raises(SystemExit) as e:
            await main.main()

        assert e.value.code == 2
        assert _awaited(api) == []

    @pytest.mark.parametrize(
        "flags",
        [
            ["--restore", "--backup"],
            ["--get-last-dump", "--restore"],
            ["--get-last-dump", "--backup"],
        ],
        ids=[
            "backup-and-restore",
            "restore-and-get-last-dump",
            "backup-and-get-last-dump",
        ],
    )
    async def test_conflicting_flags_exit_and_run_nothing(self, argv, api, flags):
        argv(*flags)

        with pytest.raises(SystemExit) as e:
            await main.main()

        assert e.value.code == 2
        assert _awaited(api) == []

    @pytest.mark.parametrize(
        ("flag", "action"),
        [
            ("--backup", "backup"),
            ("--restore", "restore"),
            ("--get-last-dump", "download_latest"),
        ],
    )
    async def test_backup_service_failure_propagates(self, argv, api, flag, action):
        argv(flag)
        api[action].side_effect = client.BackupException("service down")

        with pytest.raises(client.BackupException, match="service down"):
            await main.main()

        assert _awaited(api) == [action]
