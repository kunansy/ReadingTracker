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
    def test_no_flags(self, argv):
        argv()

        assert vars(main.parse_args()) == {
            "backup": False,
            "restore": False,
            "get_last_dump": False,
        }

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

    async def test_no_flag_does_nothing(self, argv, api):
        argv()

        await main.main()

        assert _awaited(api) == []

    @pytest.mark.parametrize(
        ("flags", "action"),
        [
            (["--restore", "--backup"], "backup"),
            (["--get-last-dump", "--restore"], "restore"),
            (["--get-last-dump", "--backup"], "backup"),
        ],
        ids=[
            "backup-over-restore",
            "restore-over-get-last-dump",
            "backup-over-get-last-dump",
        ],
    )
    async def test_only_the_first_matching_action_runs(self, argv, api, flags, action):
        argv(*flags)

        await main.main()

        assert _awaited(api) == [action]
