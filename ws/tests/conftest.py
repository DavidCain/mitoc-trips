import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def set_testing() -> None:
    os.environ["WS_DJANGO_TEST"] = "1"
