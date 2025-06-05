from __future__ import annotations

from geventsignalrclient.connection import Connection
from geventsignalrclient.connection.builder import ConnectionBuilder
from geventsignalrclient.protocol.msgpack import MessagePackHubProtocol

import logging
import time
import unittest
import warnings
from collections.abc import Callable
from typing import Any

from gevent.lock import Semaphore
from urllib3.exceptions import InsecureRequestWarning


class Urls:
    server_url_no_ssl = "ws://host.docker.internal:5000/chatHub"
    server_url_ssl = "wss://host.docker.internal:5001/chatHub"
    server_url_no_ssl_auth = "ws://host.docker.internal:5000/authHub"
    server_url_ssl_auth = "wss://host.docker.internal:5001/authHub"
    login_url_ssl = "https://host.docker.internal:5001/users/authenticate"
    login_url_no_ssl = "http://host.docker.internal:5000/users/authenticate"


class BaseTestCase(unittest.TestCase):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        self.connection: Connection
        self.connected: bool = False

        self.server_url = Urls.server_url_ssl

    def setUp(self) -> None:
        warnings.simplefilter("ignore", category=InsecureRequestWarning)
        self.connection = self.get_connection()
        self.connection.start()

        t0 = time.time()
        while not self.connected:
            time.sleep(0.1)
            if time.time() - t0 > 20:
                raise ValueError("TIMEOUT ")

    def tearDown(self) -> None:
        self.connection.stop()

    def on_open(self) -> None:
        self.connected = True

    def on_close(self) -> None:
        self.connected = False

    def release(self, lock: Semaphore) -> Callable[[], None]:
        def wrapper(*_args: Any, **_kwargs: Any) -> None:
            lock.release()

        return wrapper

    def get_connection(self, msgpack: bool = False) -> Connection:
        builder = (
            ConnectionBuilder()
            .with_url(
                self.server_url,
                options={"verify_ssl": False},
            )
            .configure_logging(
                logging.ERROR,
            )
            .with_automatic_reconnect(
                {"type": "raw", "keep_alive_interval": 10, "reconnect_interval": 5, "max_attempts": 5}
            )
        )

        if msgpack:
            builder.with_hub_protocol(MessagePackHubProtocol())

        connection = builder.build()
        connection.on_open(self.on_open)
        connection.on_close(self.on_close)

        return connection
