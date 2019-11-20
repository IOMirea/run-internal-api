import os
import logging

from typing import Any, Dict

import uvloop
import sentry_sdk

from aiohttp import web
from sentry_sdk.integrations.aiohttp import AioHttpIntegration

from .cli import args
from .rpc import setup as setup_rpc
from .config import read_config
from .logger import setup as setup_logger
from .routes import routes
from .runner import DockerRunner

DEBUG_MODE = args.verbosity == logging.DEBUG


def create_app(config: Dict[str, Any]) -> web.Application:
    app = web.Application()
    app["config"] = config
    app.add_routes(routes)

    setup_rpc(app)

    app_config = app["config"]["app"]
    app["runner"] = DockerRunner(
        app_config["max-container-ram"],
        app_config["max-container-cpu"],
        app_config["max-containers"],
    )

    return app


if __name__ == "__main__":
    config = read_config(args.config_file)

    setup_logger()

    log = logging.getLogger(__name__)

    log.info(f"running on version {os.environ['GIT_COMMIT']}")

    if args.enable_sentry:
        log.debug("initializing sentry")

        sentry_sdk.init(
            dsn=config["sentry"]["dsn"],
            integrations=[AioHttpIntegration()],
            debug=DEBUG_MODE,
        )
    else:
        log.debug("skipping sentry initialization")

    uvloop.install()

    app = create_app(config)

    web.run_app(app, host=args.host, port=args.port)
