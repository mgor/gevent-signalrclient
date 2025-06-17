from __future__ import annotations

from geventsignalrclient.connection import Connection, ConnectionBuilder
from geventsignalrclient.exceptions import HubConnectionError
from geventsignalrclient.transport import IntervalReconnectionHandler, RawReconnectionHandler

import logging

import pytest
from gevent import sleep as gsleep
from gevent.lock import Semaphore

from tests.helpers import release


def test_start_stop_open_close(signalr_server: str) -> None:
    server_url = f"wss://{signalr_server}:443/chatHub"

    connection = (
        ConnectionBuilder()
        .with_url(
            server_url,
            options={"verify_ssl": False},
        )
        .configure_logging(logging.ERROR)
        .build()
    )

    lock = Semaphore()

    connection.on_open(release(lock))
    connection.on_close(release(lock))

    assert lock.acquire(timeout=10)

    connection.start()

    assert lock.acquire(timeout=10)

    connection.stop()

    assert lock.acquire(timeout=10)


def _reconnect_test(connection: Connection) -> None:
    lock = Semaphore()

    connection.on_open(release(lock))
    connection.on_close(release(lock))

    connection.start()

    assert lock.acquire(timeout=10)

    connection.send("DisconnectMe", [])

    assert lock.acquire(timeout=10)

    connection.stop()

    assert lock.acquire(timeout=10)


def test_reconnect_interval_config(signalr_server: str) -> None:
    server_url = f"wss://{signalr_server}:443/chatHub"

    connection = (
        ConnectionBuilder()
        .with_url(
            server_url,
            options={"verify_ssl": False},
        )
        .configure_logging(
            logging.ERROR,
        )
        .with_automatic_reconnect(
            {
                "type": "interval",
                "intervals": [1, 2, 4, 45, 6, 7, 8, 9, 10],
            }
        )
        .build()
    )

    lock = Semaphore()
    connection.on_open(release(lock))
    connection.on_close(release(lock))

    assert lock.acquire(timeout=10)

    connection.start()

    assert lock.acquire(timeout=10)

    connection.stop()

    assert lock.acquire(timeout=10)

    lock.release()


def test_reconnect_interval(signalr_server: str) -> None:
    server_url = f"wss://{signalr_server}:443/chatHub"

    connection = (
        ConnectionBuilder()
        .with_url(
            server_url,
            options={"verify_ssl": False},
        )
        .configure_logging(
            logging.ERROR,
        )
        .with_automatic_reconnect(
            {
                "type": "interval",
                "intervals": [1, 2, 4, 45, 6, 7, 8, 9, 10],
                "keep_alive_interval": 3,
            }
        )
        .build()
    )

    _reconnect_test(connection)


def test_no_reconnect(signalr_server: str) -> None:
    server_url = f"wss://{signalr_server}:443/chatHub"

    connection = (
        ConnectionBuilder()
        .with_url(
            server_url,
            options={"verify_ssl": False},
        )
        .configure_logging(
            logging.ERROR,
        )
        .build()
    )

    lock = Semaphore()

    lock.acquire(timeout=10)

    connection.on_open(release(lock))

    connection.on("ReceiveMessage", release(lock))

    connection.start()

    assert lock.acquire(timeout=10)

    connection.send("DisconnectMe", [])

    assert lock.acquire(timeout=10)

    gsleep(10)

    with pytest.raises(HubConnectionError):
        connection.send("DisconnectMe", [])

    connection.stop()


def test_raw_reconnection(signalr_server: str) -> None:
    server_url = f"wss://{signalr_server}:443/chatHub"

    connection = (
        ConnectionBuilder()
        .with_url(
            server_url,
            options={"verify_ssl": False},
        )
        .configure_logging(
            logging.ERROR,
        )
        .with_automatic_reconnect({"type": "raw", "keep_alive_interval": 10, "max_attempts": 4})
        .build()
    )

    _reconnect_test(connection)


def test_raw_handler() -> None:
    handler = RawReconnectionHandler(5, 10)
    attemp = 0

    while attemp <= 10:
        assert handler.next() == 5
        attemp = attemp + 1

    with pytest.raises(ValueError):
        handler.next()


def test_reconnection_interval_handler() -> None:
    intervals = [1, 2, 4, 5, 6]
    handler = IntervalReconnectionHandler(intervals)
    for interval in intervals:
        assert handler.next() == interval

    with pytest.raises(ValueError):
        handler.next()
