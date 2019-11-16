import os
import signal
import asyncio
import logging

from copy import copy

from jarpc import Server, Request
from aiohttp import web

from .utils import run_shell_command

log = logging.getLogger(__name__)

COMMAND_UPDATE_RUNNERS = 0
COMMAND_UPDATE_LANGUAGE = 1


async def update_self(req: Request) -> None:
    log.debug("killing process")

    os.kill(os.getpid(), signal.SIGTERM)


async def update_language(req: Request, language: str) -> None:
    log.debug("updating language %s", language)

    await run_shell_command(f"docker pull iomirea/run-lang-{language}")


async def on_startup(app: web.Application) -> None:
    config = copy(app["config"]["redis-rpc"])

    host = config.pop("host")
    port = config.pop("port")

    log.debug("creating rpc connection")

    server = Server("run-api")
    server.add_command(COMMAND_UPDATE_RUNNERS, update_self)
    server.add_command(COMMAND_UPDATE_LANGUAGE, update_language)

    app["rpc"] = server

    asyncio.create_task(app["rpc"].start((host, port), **config))


async def on_cleanup(app: web.Application) -> None:
    log.debug("closing rpc connection")
    app["rpc"].close()


def setup(app: web.Application) -> None:
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
