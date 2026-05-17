from unittest import mock

from ws.conf import environments


def test_load_local_env_vars() -> None:
    with mock.patch.dict("os.environ", {"WS_MODE": "local"}):
        env_vars = dict(environments.parse_local_env_vars())

    # Spot check a couple types of variables
    assert env_vars["DATABASE_PORT"] == "5432"  # Integer-like, but it's a str
    assert env_vars["SENTRY_DSN"] == ""  # Empty
    assert env_vars["CELERY_BROKER_URL"] == "amqp://guest:guest@127.0.0.1//"
