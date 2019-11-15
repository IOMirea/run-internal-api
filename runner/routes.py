import os
import shlex
import shutil
import logging

from json import JSONDecodeError
from typing import Dict, Union

from aiohttp import web

from .utils import run_shell_command

routes = web.RouteTableDef()

log = logging.getLogger(__name__)


@routes.get("/")
async def index(req: web.Request) -> web.Response:
    return web.Response(body=f"run-runner {os.environ['GIT_COMMIT']}")


@routes.route("OPTIONS", "/health_check")
async def healthcheck(req: web.Request) -> web.Response:
    return web.Response(
        status=200
        if req.app["active_containers"] < req.app["max_active_containers"]
        else 404
    )


@routes.post("/run/{language_name}")
async def run_code(req: web.Request) -> web.Response:
    language = req.match_info["language_name"]

    try:
        data = await req.json()
    except JSONDecodeError:
        raise web.HTTPBadRequest(reason="Bad json in body")

    code = data.get("code")
    if code is None:
        raise web.HTTPBadRequest(reason="Code is missing from body")

    if req.app["active_containers"] >= req.app["max_active_containers"]:
        raise web.HTTPInternalServerError(reason="No free containers")

    req.app["active_containers"] += 1
    try:
        config = req.app["config"]["app"]

        shell_result = await run_shell_command(
            f"run_container.sh {language} {config['local-folder']} {config['host-folder']} "
            f"                 {config['container-memory']} {config['container-cpus']} "
            f"                 {shlex.quote(code)}",
            wait=True,
        )
    finally:
        req.app["active_containers"] -= 1

    folder = shell_result.stdout.split("\n")[0]
    try:
        if shell_result.exit_code != 0:
            log.error(f"Error running container. Result: {shell_result}")

            raise web.HTTPInternalServerError(reason="Error running container")

        defaults = {"exit_code": "-1", "stdout": "", "stderr": "", "exec_time": "-1"}

        result: Dict[str, Union[str, int]] = {}
        for name in defaults.keys():
            try:
                with open(f"{folder}/{name}", "r") as f:
                    result[name] = f.read()
            except FileNotFoundError:
                result[name] = defaults[name]

        result["exit_code"] = int(result["exit_code"])
        result["exec_time"] = int(result["exec_time"])
    finally:
        shutil.rmtree(folder)

    return web.json_response({**result})
