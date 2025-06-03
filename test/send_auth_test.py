from gevent_signalrclient.connection.builder import ConnectionBuilder
from gevent_signalrclient.messages import BaseMessage
from gevent_signalrclient.protocol.msgpack import MessagePackHubProtocol

import logging
import threading
import uuid

import requests

from test.base_test_case import BaseTestCase, Urls


class TestSendAuthMethod(BaseTestCase):
    server_url = Urls.server_url_ssl_auth
    login_url = Urls.login_url_ssl
    email = "test"
    password = "test"
    received = False
    message: BaseMessage | None = None
    _lock: threading._RLock | None = None

    def login(self):
        response = requests.post(
            self.login_url,
            json={
                "username": self.email,
                "password": self.password
                },verify=False)
        return response.json()["token"]

    def _setUp(self, msgpack= False):
        builder = ConnectionBuilder()\
            .with_url(self.server_url,
            options={
                "verify_ssl": False,
                "access_token_factory": self.login,
                "headers": {
                    "mycustomheader": "mycustomheadervalue"
                }
            })

        if msgpack:
            builder.with_hub_protocol(MessagePackHubProtocol())

        builder.configure_logging(logging.WARNING)\
            .with_automatic_reconnect({
                "type": "raw",
                "keep_alive_interval": 10,
                "reconnect_interval": 5,
                "max_attempts": 5
            })
        self.connection = builder.build()
        self.connection.on("ReceiveMessage", self.receive_message)
        self.connection.on_open(self.on_open)
        self.connection.on_close(self.on_close)
        self._lock = threading.Lock()
        self.assertTrue(self._lock.acquire(timeout=30))
        self.connection.start()

    def on_open(self):
        self._lock.release()

    def setUp(self):
        self._setUp()

    def receive_message(self, args):
        self._lock.release()
        self.assertEqual(args[0], self.message)

    def test_send(self):
        self.message = f"new message {uuid.uuid4()}"
        self.username = "mandrewcito"
        self.assertTrue(self._lock.acquire(timeout=30))
        self.connection.send("SendMessage", [self.message])
        self.assertTrue(self._lock.acquire(timeout=30))
        del self._lock

class TestSendNoSslAuthMethod(TestSendAuthMethod):
    server_url = Urls.server_url_no_ssl_auth
    login_url = Urls.login_url_no_ssl

class TestSendAuthMethodMsgPack(TestSendAuthMethod):
    def setUp(self):
        self._setUp(msgpack=True)

class TestSendNoSslAuthMethodMsgPack(TestSendAuthMethod):
    server_url = Urls.server_url_no_ssl_auth
    login_url = Urls.login_url_no_ssl
