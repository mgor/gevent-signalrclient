from __future__ import annotations

from geventsignalrclient.connection import Connection
from geventsignalrclient.connection.builder import ConnectionBuilder
from geventsignalrclient.exceptions import HubConnectionError
from geventsignalrclient.transport import IntervalReconnectionHandler, RawReconnectionHandler

import logging
import time

from gevent.lock import Semaphore

from tests.helpers import BaseTestCase


class TestReconnectMethods(BaseTestCase):
    def test_reconnect_interval_config(self) -> None:
        connection = (
            ConnectionBuilder()
            .with_url(
                self.server_url,
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

        _lock = Semaphore()
        connection.on_open(self.release(_lock))
        connection.on_close(self.release(_lock))

        self.assertTrue(_lock.acquire(timeout=10))

        connection.start()

        self.assertTrue(_lock.acquire(timeout=10))

        connection.stop()

        self.assertTrue(_lock.acquire(timeout=10))

        del _lock

    def test_reconnect_interval(self) -> None:
        connection = (
            ConnectionBuilder()
            .with_url(
                self.server_url,
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

        self.reconnect_test(connection)

    def test_no_reconnect(self) -> None:
        connection = (
            ConnectionBuilder()
            .with_url(
                self.server_url,
                options={"verify_ssl": False},
            )
            .configure_logging(
                logging.ERROR,
            )
            .build()
        )

        _lock = Semaphore()

        _lock.acquire(timeout=10)

        connection.on_open(self.release(_lock))

        connection.on("ReceiveMessage", self.release(_lock))

        connection.start()

        self.assertTrue(_lock.acquire(timeout=10))  # Released on ReOpen

        connection.send("DisconnectMe", [])

        self.assertTrue(_lock.acquire(timeout=10))

        time.sleep(10)

        self.assertRaises(
            HubConnectionError,
            lambda: connection.send("DisconnectMe", []),
        )

        connection.stop()
        del _lock

    def reconnect_test(self, connection: Connection) -> None:
        _lock = Semaphore()

        connection.on_open(self.release(_lock))

        connection.start()

        self.assertTrue(_lock.acquire(timeout=10))  # Release on Open

        connection.send("DisconnectMe", [])

        self.assertTrue(_lock.acquire(timeout=10))  # released on open

        connection.stop()
        del _lock

    def test_raw_reconnection(self) -> None:
        connection = (
            ConnectionBuilder()
            .with_url(
                self.server_url,
                options={"verify_ssl": False},
            )
            .configure_logging(
                logging.ERROR,
            )
            .with_automatic_reconnect({"type": "raw", "keep_alive_interval": 10, "max_attempts": 4})
            .build()
        )

        self.reconnect_test(connection)

    def test_raw_handler(self) -> None:
        handler = RawReconnectionHandler(5, 10)
        attemp = 0

        while attemp <= 10:
            self.assertEqual(handler.next(), 5)
            attemp = attemp + 1

        self.assertRaises(ValueError, handler.next)

    def test_interval_handler(self) -> None:
        intervals = [1, 2, 4, 5, 6]
        handler = IntervalReconnectionHandler(intervals)
        for interval in intervals:
            self.assertEqual(handler.next(), interval)
        self.assertRaises(ValueError, handler.next)

    def tearDown(self) -> None:
        pass

    def setUp(self) -> None:
        pass
