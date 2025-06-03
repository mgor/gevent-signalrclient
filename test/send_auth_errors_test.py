from __future__ import annotations

from gevent_signalrclient.connection.builder import ConnectionBuilder
from gevent_signalrclient.messages import BaseMessage
from gevent_signalrclient.protocol.msgpack import MessagePackHubProtocol

import logging

import requests

from test.base_test_case import BaseTestCase, Urls


class TestSendAuthErrorMethod(BaseTestCase):
    server_url = Urls.server_url_ssl_auth
    login_url = Urls.login_url_ssl
    email = "test"
    password = "ff"
    received = False
    message: BaseMessage | None = None

    def login(self):
        response = requests.post(
            self.login_url,
            json={
                "username": self.email,
                "password": self.password
                },verify=False)
        if response.status_code == 200:
            return response.json()["token"]
        raise requests.exceptions.ConnectionError()

    def setUp(self):
        pass

    def test_send_json(self):
        self._test_send(msgpack=False)

    def test_send_msgpack(self):
        self._test_send(msgpack=True)

    def _test_send(self, msgpack=False):
        builder = ConnectionBuilder()\
            .with_url(self.server_url,
            options={
                "verify_ssl": False,
                "access_token_factory": self.login,
            })

        if msgpack:
            builder.with_hub_protocol(MessagePackHubProtocol())

        builder.configure_logging(logging.ERROR)
        self.connection = builder.build()
        self.connection.on_open(self.on_open)
        self.connection.on_close(self.on_close)
        self.assertRaises(requests.exceptions.ConnectionError, lambda :self.connection.start())


class TestSendNoSslAuthMethod(TestSendAuthErrorMethod):
    server_url = Urls.server_url_no_ssl_auth
    login_url = Urls.login_url_no_ssl
