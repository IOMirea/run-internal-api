import os
import signal
import asyncio
import logging

from copy import copy

from jarpc import Server, Request
from aiohttp import web

log = logging.getLogger(__name__)

COMMAND_UPDATE_RUNNERS = 0


async def update(req: Request) -> None:
    log.debug("killing process")

    os.kill(os.getpid(), signal.SIGTERM)


async def on_startup(app: web.Application) -> None:
    config = copy(app["config"]["redis-rpc"])

    host = config.pop("host")
    port = config.pop("port")

    log.debug("creating rpc connection")

    server = Server("run-api")
    server.add_command(COMMAND_UPDATE_RUNNERS, update)

    app["rpc"] = server

    asyncio.create_task(app["rpc"].start((host, port), **config))


async def on_cleanup(app: web.Application) -> None:
    log.debug("closing rpc connection")
    app["rpc"].close()


def setup(app: web.Application) -> None:
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
