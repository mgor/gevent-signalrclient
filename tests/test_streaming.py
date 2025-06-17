from __future__ import annotations

from geventsignalrclient.connection import ConnectionBuilder
from geventsignalrclient.messages import CompletionMessage, Subject
from geventsignalrclient.protocol import MessagePackHubProtocol

import logging
from itertools import product
from typing import Any

import pytest
from gevent.lock import Semaphore
from pytest_mock.plugin import MockerFixture

from tests.helpers import SOME, release


@pytest.mark.parametrize("transport,data", product(["https", "http"], ["json", "msgpack"]))
def test_client_stream(signalr_server: str, transport: str, data: str) -> None:
    protocol = "wss" if transport == "https" else "ws"
    port = 443 if transport == "https" else 80
    server_url = f"{protocol}://{signalr_server}:{port}/chatHub"
    builder = ConnectionBuilder().with_url(
        server_url,
        options={
            "verify_ssl": False,
        },
    )

    if data == "msgpack":
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
    connection = builder.build()
    lock = Semaphore()
    items = list(range(0, 10))
    subject = Subject()

    connection.on_open(release(lock))
    connection.on_close(release(lock))

    assert lock.acquire(timeout=10)

    connection.start()

    assert lock.acquire(timeout=10)

    connection.send("UploadStream", subject)

    while len(items) > 0:
        subject.next(items.pop(0))

    subject.complete()

    connection.stop()
    assert lock.acquire(timeout=10)


@pytest.mark.parametrize("transport,data", product(["https", "http"], ["json", "msgpack"]))
def test_stream(mocker: MockerFixture, signalr_server: str, transport: str, data: str) -> None:
    protocol = "wss" if transport == "https" else "ws"
    port = 443 if transport == "https" else 80
    server_url = f"{protocol}://{signalr_server}:{port}/chatHub"
    builder = ConnectionBuilder().with_url(
        server_url,
        options={
            "verify_ssl": False,
        },
    )

    if data == "msgpack":
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
    connection = builder.build()
    items = list(range(0, 10))
    lock = Semaphore()
    lock_completed = Semaphore()

    def on_next(*_args: Any, **_kwargs: Any) -> None:
        release(lock)()
        lock.acquire(timeout=10)

    def on_complete(*_args: Any, **_kwargs: Any) -> None:
        release(lock_completed)()
        release(lock)()

    def on_error(*_args: Any, **_kwargs: Any) -> None:
        pass

    on_next_spy = mocker.Mock(wraps=on_next)
    on_complete_spy = mocker.Mock(wraps=on_complete)
    on_error_spy = mocker.Mock(wraps=on_error)

    connection.on_open(release(lock))
    connection.on_close(release(lock))

    assert lock.acquire(timeout=10)
    assert lock_completed.acquire(timeout=10)

    connection.start()

    assert lock.acquire(timeout=10)

    connection.stream(
        "Counter",
        (
            len(items),
            500,
        ),
    ).subscribe(
        {
            "next": on_next_spy,
            "complete": on_complete_spy,
            "error": on_error_spy,
        }
    )

    assert lock_completed.acquire(timeout=30)
    assert lock.acquire(timeout=10)

    connection.stop()

    on_next_spy.assert_has_calls([mocker.call(n) for n in range(0, 10)])
    on_complete_spy.assert_called_once_with(SOME(CompletionMessage, result=None, error=None))
    on_error_spy.assert_not_called()


def test_stream_error(signalr_server: str) -> None:
    server_url = f"wss://{signalr_server}:443/chatHub"
    builder = (
        ConnectionBuilder()
        .with_url(
            server_url,
            options={
                "verify_ssl": False,
            },
        )
        .configure_logging(
            logging.WARNING,
        )
        .with_automatic_reconnect(
            {
                "type": "raw",
                "keep_alive_interval": 10,
                "reconnect_interval": 5,
                "max_attempts": 5,
            }
        )
    )
    connection = builder.build()
    lock = Semaphore()
    items = list(range(0, 10))

    def on_next(*_args: Any, **_kwargs: Any) -> None:
        pass

    connection.on_open(release(lock))
    connection.on_close(release(lock))

    assert lock.acquire(timeout=10)

    connection.start()

    assert lock.acquire(timeout=10)

    my_stream = connection.stream(
        "Counter",
        (
            len(items),
            500,
        ),
    )

    with pytest.raises(TypeError):
        my_stream.subscribe(None)  # type: ignore[arg-type]

    with pytest.raises(TypeError):
        my_stream.subscribe([on_next])  # type: ignore[arg-type]

    with pytest.raises(KeyError):
        my_stream.subscribe({"key": on_next})  # type: ignore[typeddict-item]

    with pytest.raises(ValueError):
        my_stream.subscribe(
            {
                "next": "",  # type: ignore[typeddict-item]
                "complete": 1,  # type: ignore[typeddict-item]
                "error": [],  # type: ignore[typeddict-item]
            }
        )

    connection.stop()
