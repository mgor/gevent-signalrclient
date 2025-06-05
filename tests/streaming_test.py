from __future__ import annotations

from geventsignalrclient.connection import Connection

import time
from typing import Any

from tests.helpers import BaseTestCase, Urls


class TestSendMethod(BaseTestCase):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        self.server_url = Urls.server_url_ssl
        self.received: bool = False
        self.items = list(range(0, 10))
        self.complete: bool

    def on_complete(self, _: Any) -> None:
        self.complete = True

    def on_next(self, x: int) -> None:
        item = self.items.pop(0)
        self.assertEqual(x, item)

    def test_stream(self) -> None:
        self.complete = False
        self.items = list(range(0, 10))
        self.connection.stream(
            "Counter",
            (
                len(self.items),
                500,
            ),
        ).subscribe(
            {
                "next": self.on_next,
                "complete": self.on_complete,
                "error": self.fail,  # TestcaseFail
            }
        )

        t0 = time.time()
        while not self.complete:
            time.sleep(0.1)
            if time.time() - t0 > 20:
                raise ValueError("TIMEOUT ")

    def test_stream_error(self) -> None:
        self.complete = False
        self.items = list(range(0, 10))

        my_stream = self.connection.stream(
            "Counter",
            (
                len(self.items),
                500,
            ),
        )

        with self.assertRaises(TypeError):
            my_stream.subscribe(None)  # type: ignore[arg-type]

        with self.assertRaises(TypeError):
            my_stream.subscribe([self.on_next])  # type: ignore[arg-type]

        with self.assertRaises(KeyError):
            my_stream.subscribe({"key": self.on_next})  # type: ignore[typeddict-item]

        with self.assertRaises(ValueError):
            my_stream.subscribe(
                {
                    "next": "",  # type: ignore[typeddict-item]
                    "complete": 1,  # type: ignore[typeddict-item]
                    "error": [],  # type: ignore[typeddict-item]
                }
            )


class TestSendNoSslMethod(TestSendMethod):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        self.server_url = Urls.server_url_no_ssl


class TestSendMethodMsgPack(TestSendMethod):
    def get_connection(self, msgpack: bool = False) -> Connection:
        return super().get_connection(msgpack=True)


class TestSendMethodNoSslMsgPack(TestSendNoSslMethod):
    def get_connection(self, msgpack: bool = False) -> Connection:
        return super().get_connection(msgpack=True)
