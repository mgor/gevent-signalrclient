from __future__ import annotations

from geventsignalrclient.connection import ConnectionBuilder

import logging

import pytest
import websocket
from gevent.lock import Semaphore

from tests.helpers import release


def test_conf_bad_auth_function(signalr_server: str) -> None:
    server_url = f"wss://{signalr_server}:443/chatHub"

    with pytest.raises(TypeError):
        ConnectionBuilder().with_url(
            server_url,
            options={
                "verify_ssl": False,
                "access_token_factory": 1234,
                "headers": {"mycustomheader": "mycustomheadervalue"},
            },
        )


def test_conf_bad_url() -> None:
    with pytest.raises(ValueError):
        ConnectionBuilder().with_url("")


def test_conf_bad_options(signalr_server: str) -> None:
    server_url = f"wss://{signalr_server}:443/chatHub"

    with pytest.raises(TypeError):
        ConnectionBuilder().with_url(
            server_url,
            options=["ssl", True],  # type: ignore[arg-type]
        )


def test_conf_auth_configured(signalr_server: str) -> None:
    server_url = f"wss://{signalr_server}:443/chatHub"

    with pytest.raises(TypeError):
        connection = ConnectionBuilder().with_url(
            server_url,
            options={
                "verify_ssl": False,
                "access_token_factory": "",
                "headers": {"mycustomheader": "mycustomheadervalue"},
            },
        )
        connection.build()


def test_conf_enable_trace(signalr_server: str) -> None:
    server_url = f"wss://{signalr_server}:443/chatHub"

    connection = (
        ConnectionBuilder()
        .with_url(
            server_url,
            options={"verify_ssl": False},
        )
        .configure_logging(
            logging.WARNING,
            socket_trace=True,
        )
        .with_automatic_reconnect(
            {"type": "raw", "keep_alive_interval": 10, "reconnect_interval": 5, "max_attempts": 5}
        )
        .build()
    )

    lock = Semaphore()
    lock.acquire()

    connection.on_open(release(lock))
    connection.on_close(release(lock))

    try:
        connection.start()
        assert websocket.isEnabledForDebug()
        websocket.enableTrace(False)
    finally:
        for name in ["gevent-signalrcore", "websocket"]:
            logger = logging.getLogger(name)

            for handler in logger.handlers[:]:
                if isinstance(handler, logging.StreamHandler):
                    logger.removeHandler(handler)

        lock.acquire()
        connection.stop()
