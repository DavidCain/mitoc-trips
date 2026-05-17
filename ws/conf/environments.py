import enum
import importlib.resources
import logging
import os
import sys

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
    """TEMPORARY method to support loading settings.py in Docker.

    When developing locally, direnv will autoload ws/conf/local.env

    We sometimes want to call manage.py commands in a Dockerfile
    without crashing settings.py trying to load secrets.

    Deploy some janky code to mimic `source ws/conf/local.env` in
    Python code.
    """
    for export_line in (
        line.strip()
        for line in importlib.resources.open_text(conf, "local.env")
        if line.strip() and not line.startswith("#")
    ):
        varname, value = export_line.split("=", maxsplit=1)
        assert " " not in value
        assert "\\" not in value, f"Will intepret {value} as plain Python!"
        os.environ[varname] = value
