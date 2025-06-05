# Gevent SignalR client

This is a fork of the great work done by [mandrewcito (donate)](https://www.paypal.me/mandrewcito/1) in [mandrewcito/signalrcore](https://github.com/mandrewcito/signalrcore).

See his [dev posts article series, with library examples and implementation](https://dev.to/mandrewcito/singlar-core-python-client-58e7).

A fork and rewrite was needed to get a SignalR client that would work good in combination with other `gevent` driven projects. When doing this types was also added, and some major restructuring
of the code (modules and packages).

# Develop

Test server are avaiable [here](https://github.com/mandrewcito/signalrcore-containertestservers) and docker compose is required.

```bash
git clone https://github.com/mandrewcito/signalrcore-containertestservers
cd signalrcore-containertestservers
docker-compose up -d
```

# Example

Here is an example on a client implementation that can be used with [grizzly](https://github.com/biometria-se/grizzly). This client is used to connect to an SignalR hub where it is possible to subscribe (and unsubscribe), via methods `Subscribe` and `Unsubscribe` respectivly, to get a subset of all messages that are published on the hub.

Each method that is received has its own internal `Queue`, where its then possible to get the messages from, when needed. Grizzlys method from providing an access token (Azure AAD) is used.

```python
from dataclasses import dataclass, field
from typing import Any, ClassVar, Callable, cast
from typing_extensions import Self
from time import perf_counter
from datetime import datetime, timezone
from contextlib import suppress
from copy import deepcopy

from gevent.queue import Queue, Empty
from gevent.lock import Semaphore, DummySemaphore
from gevent import sleep as gsleep

from geventsignalrclient.connection.builder import ConnectionBuilder
from geventsignalrclient.messages import ErrorMessage

from grizzly.users import RestApiUser
from grizzly.auth import refresh_token, AAD
from grizzly.types import GrizzlyResponse, RequestMethod
from grizzly.tasks import RequestTask
from grizzly.utils import merge_dicts


@dataclass
class SignalRBuilder:
    hub: str = field(init=True)
    url: str = field(init=False)
    auth: dict | None  = field(init=False, default=None)

    user: RestApiUser = field(init=False)
    on_start: bool = field(init=False)

    def with_url(self, url: str) -> Self:
        self.url = url

        return self

    def with_user(self, user: RestApiUser) -> Self:
        self.user = user
        self.logger = user.logger

        return self

    def with_auth(self, auth: dict | None) -> Self:
        self.auth = auth

        return self

    def with_logger(self, logger: logging.Logger) -> Self:
        self.logger = logger

        return self

    def with_log_level(self, level: logging._Level) -> Self:
        self.logger.setLevel(level)

        return self

    def with_on_start(self, on_start: bool) -> Self:
        self.on_start = on_start

        return self


class SignalRClient:
    def __init__(self, builder: SignalRBuilder, connection_hash: str, methods: set[str]) -> None:
        self.connection_hash = connection_hash
        self.logger = logging.getLogger(f'{builder.user.__class__.__name__}/{id(builder.user)}/signalr/{builder.hub}')
        self._lock: Semaphore = Semaphore(1)

        self.connection = ConnectionBuilder().with_url(
            builder.url,
            options={
                'access_token_factory': self.token_factory(builder),
                'verify_ssl': True,
                'skip_negotiation': False,
                'headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36 Edg/135.0.0.0',
                },
            },
        ).with_automatic_reconnect({
            'type': 'interval',
            'keep_alive_interval': 10,
            'intervals': [1, 3, 5, 7, 15],
        }).with_logger(
            self.logger,
        ).build()

        if builder.auth is None:
            builder.auth = deepcopy(builder.user._context['auth'])

        self.user = builder.user
        self.hub = builder.hub
        self.channel: str | None = None
        self.logger.setLevel(builder.user.logger.getEffectiveLevel())

        self.on_start: bool = builder.on_start
        self.queues: dict[str, Queue[dict[str, Any]]] = {}
        self.methods: set[str] = set()

        for method in methods:
            self.on_method(method)

        self._has_reconnected: bool = False

        self.connection.on_open(self.on_open)
        self.connection.on_close(self.on_close)
        self.connection.on_error(self.on_error)
        self.connection.on_reconnect(self.on_reconnect)
        self.connection.on('client_result', self.on_client_result)

        logging.getLogger('websocket').setLevel(logging.ERROR)

        self._lock.acquire()
        self.connection.start()
        self._lock.wait(timeout=30)

        self._connected: bool = True

    def lock(self, *, use_lock: bool = True) -> Semaphore:
        return self._lock if use_lock else DummySemaphore()

    def on_method(self, method: str) -> None:
        with self.lock():
            if method not in self.methods:
                self.logger.info('registered handler for method %s on hub %s', method, self.hub)
                self.connection.on(method, self.on_message(method))
                self.queues.update({method: Queue()})
                self.methods.add(method)

    def reset_queues(self) -> None:
        self.queues.clear()

        for method in self.methods:
            self.queues.update({method: Queue()})

    def subscribe(self, channel: str) -> None:
        with self.lock(use_lock=self._lock.ready()):
            if not self._has_reconnected:
                self.reset_queues()

            self.connection.send('Subscribe', [channel])
            self.logger.info('subscribed to channel %s on hub %s', channel, self.hub)
            self.channel = channel

    def unsubscribe(self, channel: str) -> None:
        with self.lock():
            self.connection.send('Unsubscribe', [channel])
            self.logger.info('unsubscribed to channel %s on hub %s', channel, self.hub)
            self.channel = None

            self.reset_queues()

            if not self.on_start:
                with suppress(Exception):
                    self.connection.stop()

    def token_factory(cls, builder: SignalRBuilder) -> Callable[[], str] | None:
        def _token_factory() -> str:
            def dummy(client: RestApiUser, arg: Any, *args: Any, **kwargs: Any) -> GrizzlyResponse:
                return {}, None

            original_auth: dict | None = None

            if builder.user.credential is not None and builder.user.credential._access_token is not None:
                expires_on = datetime.fromtimestamp(builder.user.credential._access_token.expires_on, tz=timezone.utc).astimezone(None)
                if expires_on < datetime.now(tz=timezone.utc):
                    return builder.user.credential._access_token.token

            if builder.auth is not None:
                original_auth = deepcopy(builder.user._context['auth'])
                builder.user._context['auth'] = merge_dicts(builder.user._context['auth'], builder.auth)

            try:
                refresh_token(AAD)(dummy)(builder.user, RequestTask(RequestMethod.GET, 'token-generator', '/dev/null'))
            finally:
                if original_auth is not None:
                    builder.user._context['auth'] = merge_dicts(builder.user._context['auth'], original_auth)

            assert isinstance(builder.user, RestApiUser)
            assert builder.user.credential is not None

            if builder.user.credential._access_token is None:
                message = f'no access token for {builder.user.__class__.__name__}'
                raise RuntimeError(message)

            return builder.user.credential._access_token.token

        return _token_factory

    def on_open(self) -> None:
        if self._has_reconnected and self.channel is not None:
            self.subscribe(self.channel)

        if self._lock is not None:
            self._lock.release()

    def on_close(self) -> None:
        if not self._connected:
            return

        self.logger.info('disconnected from hub %s', self.hub)
        self._connected = False

    def on_reconnect(self) -> None:
        self.logger.info('reconnected to hub %s, subscribed to channel %s', self.hub, self.channel)
        self._has_reconnected = True
        self._lock.acquire()

    def on_error(self, message: ErrorMessage) -> None:
        self.logger.error(message.error)

    def on_message(self, method: str) -> Callable[[list], None]:
        def wrapper(messages: list[dict[str, Any]]) -> None:
            current_size = self.queues[method].qsize()
            message_count = len(messages)

            with self._lock:
                for message in messages:
                    message.update({'__timestamp__': datetime.now(tz=timezone.utc).isoformat()})
                    try:
                        self.queues[method].put_nowait(message)
                    except KeyError:
                        # this can happen if a message is received just after unsubscription from channel
                        # i.e. a message is pushed after the client has sent unsubscribed, but before the
                        # server actually has unsubscribed the client
                        return

                self.logger.debug('added %d %s messages in queue with size %d: %r', message_count, method, current_size, messages)

        return wrapper

    def on_client_result(self, messages: list[dict[str, Any]]) -> str:
        self.logger.debug('received client result: %r', messages)
        return 'reply'

    def get(self, method: str, *, timeout: float = 60.0) -> dict[str, Any]:
        count = 0
        start = perf_counter()

        while True:
            count += 1
            try:
                return cast(dict[str, Any], self.queues[method].get_nowait())
            except Empty:
                delta = perf_counter() - start

                if count % 20 == 0:
                    count = 0
                    self.logger.debug('still no %s message received within %.2f seconds', method, delta)

                if delta >= timeout:
                    message = f'no {method} message received with in {delta:.0f} seconds, bailing out'
                    raise ValueError(message)

                gsleep(0.5)
```
