from __future__ import annotations

from geventsignalrclient.exceptions import HubConnectionError
from geventsignalrclient.messages import BaseMessage, CompletionMessage, ErrorMessage

import time
import uuid
from typing import Any

from gevent.lock import Semaphore

from tests.helpers import BaseTestCase, Urls


class TestSendException(BaseTestCase):
    def receive_message(self, _: Any):
        raise Exception()

    def setUp(self) -> None:
        self.connection = self.get_connection()
        self.connection.start()

        while not self.connected:
            time.sleep(0.1)

    def test_send_exception(self) -> None:
        self.connection.send("SendMessage", ["user", "msg"])

    def test_hub_error(self) -> None:
        _lock = Semaphore()

        def on_error(error: ErrorMessage) -> None:
            _lock.release()

        self.assertTrue(_lock.acquire(timeout=10))
        self.connection.on_error(on_error)

        def on_message(_: Any) -> None:
            _lock.release()
            self.assertTrue(_lock.acquire(timeout=10))

        self.connection.on("ThrowExceptionCall", on_message)
        self.connection.send("ThrowException", ["msg"])


class TestSendExceptionMsgPack(TestSendException):
    def setUp(self) -> None:
        self.connection = self.get_connection(msgpack=True)
        self.connection.start()

        while not self.connected:
            time.sleep(0.1)

class TestSendWarning(BaseTestCase):
    def setUp(self) -> None:
        self.connection = self.get_connection()
        self.connection.start()
        while not self.connected:
            time.sleep(0.1)

    def test_send_warning(self) -> None:
        _lock = Semaphore()
        _lock.acquire()

        def on_invocation(message: BaseMessage) -> None:
            nonlocal _lock
            _lock.release()

        self.connection.send("SendMessage", ["user", "msg"], on_invocation)
        self.assertTrue(_lock.acquire(timeout=10))
        del _lock

class TestSendWarningMsgPack(TestSendWarning):
    def setUp(self) -> None:
        self.connection = super().get_connection(msgpack=True)
        self.connection.start()

        while not self.connected:
            time.sleep(0.1)


class TestSendMethod(BaseTestCase):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        self.received: bool = False

    def setUp(self) -> None:
        self.connection = self.get_connection()
        self.connection.on("ReceiveMessage", self.receive_message)
        self.connection.start()

        while not self.connected:
            time.sleep(0.1)

    def receive_message(self, args: list) -> None:
        self.assertEqual(args[1], self.message)
        self.received = True

    def test_send_bad_args(self) -> None:
        class A:
            pass

        with self.assertRaises(TypeError):
            self.connection.send("SendMessage", A())  # type: ignore[arg-type]

    def test_send(self) -> None:
        self.message = f"new message {uuid.uuid4()}"
        self.username = "mandrewcito"
        self.received = False
        self.connection.send("SendMessage", [self.username, self.message])

        while not self.received:
            time.sleep(0.1)

        self.assertTrue(self.received)

    def test_send_with_callback(self) -> None:
        self.message = f"new message {uuid.uuid4()}"
        self.username = "mandrewcito"
        self.received = False
        _lock = Semaphore()
        _lock.acquire()
        uid = str(uuid.uuid4())

        def release(m: BaseMessage) -> None:
            nonlocal _lock
            assert isinstance(m, CompletionMessage)
            self.assertTrue(m.invocation_id, uid)
            _lock.release()

        self.connection.send(
            "SendMessage",
            [self.username, self.message],
            release,
            invocation_id=uid,
        )

        self.assertTrue(_lock.acquire(timeout=10))
        del _lock

class TestSendNoSslMethod(TestSendMethod):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        self.server_url = Urls.server_url_no_ssl

class TestSendMethodMsgPack(TestSendMethod):
    def setUp(self) -> None:
        self.connection = super().get_connection(msgpack=True)
        self.connection.on("ReceiveMessage", super().receive_message)
        self.connection.start()

        while not self.connected:
            time.sleep(0.1)

class TestSendNoSslMethodMsgPack(TestSendMethodMsgPack):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        self.server_url = Urls.server_url_no_ssl

class TestSendErrorMethod(BaseTestCase):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        self.received: bool = False

    def setUp(self) -> None:
        self.connection = self.get_connection()
        self.connection.on("ReceiveMessage", self.receive_message)

    def receive_message(self, args: list) -> None:
        self.assertEqual(args[1], self.message)
        self.received = True

    def test_send_with_error(self) -> None:
        self.message = f"new message {uuid.uuid4()}"
        self.username = "mandrewcito"

        with self.assertRaises(HubConnectionError):
            self.connection.send("SendMessage", [self.username, self.message])

        self.connection.start()

        while not self.connected:
            time.sleep(0.1)

        self.received = False
        self.connection.send("SendMessage", [self.username, self.message])

        while not self.received:
            time.sleep(0.1)

        self.assertTrue(self.received)


class TestSendErrorNoSslMethod(TestSendErrorMethod):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        self.server_url = Urls.server_url_no_ssl


class TestSendErrorMethodMsgPack(TestSendErrorMethod):
    def get_connection(self):
        return super().get_connection(msgpack=True)

class TestSendErrorNoSslMethodMsgPack(TestSendErrorNoSslMethod):
    def get_connection(self):
        return super().get_connection(msgpack=True)
