from __future__ import annotations

from geventsignalrclient.connection.builder import ConnectionBuilder

import logging

from gevent.lock import Semaphore

from tests.helpers import BaseTestCase


class TestClientStreamMethod(BaseTestCase):
    def setUp(self) -> None:
        pass

    def tearDown(self) -> None:
        pass


    def test_start(self) -> None:
        connection = ConnectionBuilder().with_url(
            self.server_url,
            options={"verify_ssl": False},
        ).configure_logging(logging.ERROR).build()

        _lock = Semaphore()

        self.assertTrue(_lock.acquire(timeout=30))

        connection.on_open(self.release(_lock))
        connection.on_close(self.release(_lock))

        connection.start()

        self.assertTrue(_lock.acquire(timeout=30))  # Released on open

        connection.start()

        connection.stop()

    def test_open_close(self) -> None:
        self.connection = self.get_connection()

        _lock = Semaphore()

        self.connection.on_open(self.release(_lock))
        self.connection.on_close(self.release(_lock))

        self.assertTrue(_lock.acquire())

        self.connection.start()

        self.assertTrue(_lock.acquire())

        self.connection.stop()

        self.assertTrue(_lock.acquire())

        _lock.release()
        del _lock
