from __future__ import annotations

from gevent_signalrclient.connection.builder import ConnectionBuilder

import logging
import threading

from test.base_test_case import BaseTestCase


class TestClientStreamMethod(BaseTestCase):
    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_start(self):
        connection = ConnectionBuilder()\
            .with_url(self.server_url, options={"verify_ssl": False})\
            .configure_logging(logging.ERROR)\
            .build()

        _lock = threading.Lock()
        self.assertTrue(_lock.acquire(timeout=30))


        connection.on_open(lambda: _lock.release())
        connection.on_close(lambda: _lock.release())

        connection.start()

        self.assertTrue(_lock.acquire(timeout=30))  # Released on open

        result = connection.start()

        self.assertFalse(result)

        connection.stop()

    def test_open_close(self):
        self.connection = self.get_connection()

        _lock = threading.Lock()

        self.connection.on_open(lambda: _lock.release())  # noqa: F821
        self.connection.on_close(lambda: _lock.release())  # noqa: F821

        self.assertTrue(_lock.acquire())

        self.connection.start()

        self.assertTrue(_lock.acquire())

        self.connection.stop()

        self.assertTrue(_lock.acquire())

        _lock.release()
        del _lock
