from __future__ import annotations

from geventsignalrclient.connection.builder import ConnectionBuilder
from geventsignalrclient.messages import BaseMessage
from geventsignalrclient.protocol.msgpack import MessagePackHubProtocol

import logging
from typing import Any

import requests

from tests.helpers import BaseTestCase, Urls


class TestSendAuthErrorMethod(BaseTestCase):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        self.server_url = Urls.server_url_ssl_auth
        self.login_url = Urls.login_url_ssl
        self.email = "test"
        self.password = "ff"
        self.received = False
        self.message: BaseMessage | str | None = None

    def login(self) -> str:
        response = requests.post(
            self.login_url,
            json={
                "username": self.email,
                "password": self.password,
            },
            verify=False,
        )

        if response.status_code == 200:
            return response.json()["token"]

        raise requests.exceptions.ConnectionError()

    def setUp(self) -> None:
        pass

    def test_send_json(self) -> None:
        self._test_send(msgpack=False)

    def test_send_msgpack(self) -> None:
        self._test_send(msgpack=True)

    def _test_send(self, msgpack: bool = False) -> None:
        builder = ConnectionBuilder().with_url(
            self.server_url,
            options={
                "verify_ssl": False,
                "access_token_factory": self.login,
            },
        )

        if msgpack:
            builder.with_hub_protocol(MessagePackHubProtocol())

        builder.configure_logging(logging.ERROR)
        self.connection = builder.build()
        self.connection.on_open(self.on_open)
        self.connection.on_close(self.on_close)
        self.assertRaises(requests.exceptions.ConnectionError, self.connection.start)


class TestSendNoSslAuthMethod(TestSendAuthErrorMethod):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        self.server_url = Urls.server_url_no_ssl_auth
        self.login_url = Urls.login_url_no_ssl
