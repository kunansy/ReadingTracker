import runpy
from pathlib import Path

from gunicorn.config import Config

GUNICORN_CONF = Path(__file__).resolve().parents[2] / "gunicorn.conf.py"
HOOKS = {"on_starting", "post_fork"}


def test_gunicorn_conf_names_do_not_override_settings():
    namespace = runpy.run_path(str(GUNICORN_CONF))

    clashes = (namespace.keys() & Config().settings.keys()) - HOOKS

    assert clashes == set()
