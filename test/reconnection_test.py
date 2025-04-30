from __future__ import annotations

from signalrcore.exceptions import HubConnectionError
from signalrcore.connection.builder import ConnectionBuilder
from signalrcore.transport import IntervalReconnectionHandler, RawReconnectionHandler

import logging
import threading
import time

from test.base_test_case import BaseTestCase


class TestReconnectMethods(BaseTestCase):

    def receive_message(self, args):
        self.assertEqual(args[1], self.message)
        self.received = True

    def test_reconnect_interval_config(self):
        connection = ConnectionBuilder()\
            .with_url(self.server_url, options={"verify_ssl": False})\
            .configure_logging(logging.ERROR)\
            .with_automatic_reconnect({
                "type": "interval",
                "intervals": [1, 2, 4, 45, 6, 7, 8, 9, 10]
            })\
            .build()
        _lock = threading.Lock()
        connection.on_open(lambda: _lock.release())  # noqa: F821
        connection.on_close(lambda: _lock.release())  # noqa: F821

        self.assertTrue(_lock.acquire(timeout=10))

        connection.start()

        self.assertTrue(_lock.acquire(timeout=10))

        connection.stop()

        self.assertTrue(_lock.acquire(timeout=10))

        del _lock

    def test_reconnect_interval(self):
        connection = ConnectionBuilder()\
            .with_url(self.server_url, options={"verify_ssl": False})\
            .configure_logging(logging.ERROR)\
            .with_automatic_reconnect({
                "type": "interval",
                "intervals": [1, 2, 4, 45, 6, 7, 8, 9, 10],
                "keep_alive_interval": 3
            })\
            .build()
        self.reconnect_test(connection)

    def test_no_reconnect(self):
        connection = ConnectionBuilder()\
            .with_url(self.server_url, options={"verify_ssl": False})\
            .configure_logging(logging.ERROR)\
            .build()

        _lock = threading.Lock()

        _lock.acquire(timeout=10)

        connection.on_open(lambda: _lock.release())  # noqa: F821

        connection.on("ReceiveMessage", lambda _: _lock.release())  # noqa: F821

        connection.start()

        self.assertTrue(_lock.acquire(timeout=10))  # Released on ReOpen

        connection.send("DisconnectMe", [])

        self.assertTrue(_lock.acquire(timeout=10))

        time.sleep(10)

        self.assertRaises(
            HubConnectionError,
            lambda: connection.send("DisconnectMe", []))

        connection.stop()
        del _lock

    def reconnect_test(self, connection):
        _lock = threading.RLock()

        connection.on_open(lambda: _lock.release())  # noqa: F821

        connection.start()

        self.assertTrue(_lock.acquire(timeout=10)) # Release on Open

        connection.send("DisconnectMe", [])

        self.assertTrue(_lock.acquire(timeout=10)) # released on open

        connection.stop()
        del _lock

    def test_raw_reconnection(self):
        connection = ConnectionBuilder()\
            .with_url(self.server_url, options={"verify_ssl": False})\
            .configure_logging(logging.ERROR)\
            .with_automatic_reconnect({
                "type": "raw",
                "keep_alive_interval": 10,
                "max_attempts": 4
            })\
            .build()

        self.reconnect_test(connection)

    def test_raw_handler(self):
        handler = RawReconnectionHandler(5, 10)
        attemp = 0

        while attemp <= 10:
            self.assertEqual(handler.next(), 5)
            attemp = attemp + 1

        self.assertRaises(ValueError, handler.next)

    def test_interval_handler(self):
        intervals = [1, 2, 4, 5, 6]
        handler = IntervalReconnectionHandler(intervals)
        for interval in intervals:
            self.assertEqual(handler.next(), interval)
        self.assertRaises(ValueError, handler.next)

    def tearDown(self):
        pass

    def setUp(self):
        pass
