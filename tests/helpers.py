from __future__ import annotations

from abc import ABCMeta
from collections.abc import Callable
from typing import Any

import requests
from gevent.lock import Semaphore


def release(lock: Semaphore) -> Callable[[], None]:
    def wrapper(*args: Any, **kwargs: Any) -> None:
        lock.release()

    return wrapper


def access_token_factory(server: str, *, protocol: str, username: str, password: str) -> Callable[[], str]:
    def wrapper() -> str:
        response = requests.post(
            f"{protocol}://{server}/users/authenticate",
            json={
                "username": username,
                "password": password,
            },
            verify=False,
        )

        if response.status_code == 200:
            return response.json()["token"]

        raise requests.exceptions.ConnectionError()

    return wrapper


def ANY(*cls: type, message: str | None = None) -> object:  # noqa: N802
    """Compare equal to everything, as long as it is of the same type."""

    class WrappedAny(metaclass=ABCMeta):  # noqa: B024
        def __eq__(self, other: object) -> bool:
            if len(cls) < 1:
                return True

            return isinstance(other, cls) and (message is None or (message is not None and message in str(other)))

        def __ne__(self, other: object) -> bool:
            return not self.__eq__(other)

        def __neq__(self, other: object) -> bool:
            return self.__ne__(other)

        def __repr__(self) -> str:
            c = cls[0] if len(cls) == 1 else cls
            representation: list[str] = [f"<ANY({c})", ">"]

            if message is not None:
                representation.insert(-1, f", message='{message}'")

            return "".join(representation)

    for c in cls:
        WrappedAny.register(c)

    return WrappedAny()


def SOME(cls: type, *value: Any, **values: Any) -> object:  # noqa: N802
    class WrappedSome:
        def __eq__(self, other: object) -> bool:
            if issubclass(cls, dict):

                def get_value(other: Any, attr: str) -> Any:
                    return other.get(attr)
            else:

                def get_value(other: Any, attr: str) -> Any:
                    return getattr(other, attr)

            return isinstance(other, cls) and all(get_value(other, attr) == value for attr, value in values.items())

        def __ne__(self, other: object) -> bool:
            return not self.__eq__(other)

        def __neq__(self, other: object) -> bool:
            return self.__ne__(other)

        def __repr__(self) -> str:
            info = ", ".join([f"{key}={value}" for key, value in values.items()])
            return f"<SOME({cls}, {info})>"

    if len(value) > 0 and len(values) > 0:
        message = "cannot use both positional and named arguments"
        raise RuntimeError(message)

    if len(values) < 1 and len(value) < 1:
        raise AttributeError(name="values", obj=str(type))

    if len(value) > 1:
        message = "can only use 1 positional argument"
        raise RuntimeError(message)

    if len(value) > 0 and isinstance(value[0], dict):
        values = {**value[0]}

    return WrappedSome()
