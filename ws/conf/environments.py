import enum
import importlib.resources
import logging
import os
import sys
from collections.abc import Iterator

from ws import conf

logger = logging.getLogger()

RED = "\033[91m"
NC = "\033[0m"


class Mode(enum.Enum):
    TEST = "test"
    LOCAL = "local"
    DEPLOYED = "deployed"


def get_ws_mode() -> Mode:
    ws_mode = os.getenv("WS_MODE")
    if not ws_mode:
        sys.exit(
            f"{RED}Env var WS_MODE is required.{NC} "
            "For simple local dev, set WS_MODE=local"
        )
    return Mode(ws_mode)


def load_local_env_vars() -> None:
    """TEMPORARY method to support importing settings.py in Dockerfiles.

    Our Dockerfile includes a few invocations to `manage.py`, which in turn
    will necessarily need to import `settings.py`, and the current
    configuration of Django settings will complain if settings are not
    available an environment variables.

    When developing locally, direnv will autoload ws/conf/local.env

    We sometimes want to call manage.py commands in a Dockerfile
    without crashing settings.py trying to load secrets.

    This janky runtime solution mimics exporting all the env vars in
    `ws/conf/local.env`
    """
    assert get_ws_mode() == Mode.LOCAL

    for varname, value in parse_local_env_vars():
        os.environ[varname] = value


def parse_local_env_vars() -> Iterator[tuple[str, str]]:
    with importlib.resources.open_text(conf, "local.env") as env_file:
        for export_line in (
            line.strip()
            for line in env_file
            if line.strip() and not line.startswith("#")
        ):
            # We don't bother with special character handling...
            assert " " not in export_line
            assert "\\" not in export_line
            varname, value = export_line.split("=", maxsplit=1)
            yield (varname, value)
