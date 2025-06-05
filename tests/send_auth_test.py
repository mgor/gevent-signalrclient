from geventsignalrclient.connection.builder import ConnectionBuilder
from geventsignalrclient.messages import BaseMessage
from geventsignalrclient.protocol.msgpack import MessagePackHubProtocol

import logging
import uuid
from typing import Any

import requests
from gevent.lock import Semaphore

from tests.helpers import BaseTestCase, Urls


class TestSendAuthMethod(BaseTestCase):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        self.server_url = Urls.server_url_ssl_auth
        self.login_url = Urls.login_url_ssl
        self.email = "test"
        self.password = "test"
        self.received: bool = False
        self.message: BaseMessage | str | None = None
        self._lock: Semaphore

    def login(self) -> str:
        response = requests.post(
            self.login_url,
            json={"username": self.email, "password": self.password},
            verify=False,
        )

        return response.json()["token"]

    def _setUp(self, msgpack: bool = False) -> None:
        builder = ConnectionBuilder().with_url(
            self.server_url,
            options={
                "verify_ssl": False,
                "access_token_factory": self.login,
                "headers": {"mycustomheader": "mycustomheadervalue"},
            },
        )

        if msgpack:
            builder.with_hub_protocol(MessagePackHubProtocol())

        builder.configure_logging(
            logging.WARNING,
        ).with_automatic_reconnect(
            {
                "type": "raw",
                "keep_alive_interval": 10,
                "reconnect_interval": 5,
                "max_attempts": 5,
            }
        )

        self.connection = builder.build()
        self.connection.on("ReceiveMessage", self.receive_message)
        self.connection.on_open(self.on_open)
        self.connection.on_close(self.on_close)
        self._lock = Semaphore()
        self.assertTrue(self._lock.acquire(timeout=30))
        self.connection.start()

    def on_open(self) -> None:
        self._lock.release()

    def setUp(self) -> None:
        self._setUp()

    def receive_message(self, args: list) -> None:
        if self._lock is not None:
            self._lock.release()
        self.assertEqual(args[0], self.message)

    def test_send(self) -> None:
        self.message = f"new message {uuid.uuid4()}"
        self.username = "mandrewcito"
        self.assertTrue(self._lock.acquire(timeout=30))
        self.connection.send("SendMessage", [self.message])
        self.assertTrue(self._lock.acquire(timeout=30))


class TestSendNoSslAuthMethod(TestSendAuthMethod):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        self.server_url = Urls.server_url_no_ssl_auth
        self.login_url = Urls.login_url_no_ssl


class TestSendAuthMethodMsgPack(TestSendAuthMethod):
    def setUp(self) -> None:
        self._setUp(msgpack=True)


class TestSendNoSslAuthMethodMsgPack(TestSendAuthMethod):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        self.server_url = Urls.server_url_no_ssl_auth
        self.login_url = Urls.login_url_no_ssl
