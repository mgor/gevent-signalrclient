from __future__ import annotations

import atexit
import logging
from pathlib import Path
from time import perf_counter

import docker
import pytest
import requests
from gevent import sleep as gsleep
from gevent.lock import Semaphore

lock = Semaphore()


def wait_for_url(url: str, timeout: int = 30) -> None:
    start = perf_counter()
    while True:
        try:
            response = requests.get(url, timeout=1, verify=False)

            if response.status_code in [200, 401, 403]:
                break
        except requests.exceptions.RequestException:
            logging.exception("signalr server not started")

            if start - perf_counter() > timeout:
                raise TimeoutError("signalr server not started in time")

            gsleep(1.5)


@pytest.fixture(scope="session")
def signalr_server() -> str:
    client = docker.from_env()

    image_name = "server_signalr"
    name = f"{image_name}_{id(lock)}"

    with lock:
        client.images.build(
            path=Path(__file__).parent.joinpath("SignalRSample/src").as_posix(),
            tag=image_name,
        )

        try:
            container = client.containers.get(name)
        except docker.errors.NotFound:
            container = client.containers.run(
                image=image_name,
                name=name,
                environment={
                    "ASPNETCORE_ENVIRONMENT": "Development",
                    "ASPNETCORE_URLS": "http://*;https://*",
                },
                detach=True,
                remove=True,
            )

            atexit.register(container.stop)
            container.reload()

        ip_address = container.attrs["NetworkSettings"]["IPAddress"]

        wait_for_url(f"https://{ip_address}")

        return ip_address
