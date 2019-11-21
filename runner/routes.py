import os
import logging

from json import JSONDecodeError

from aiohttp import web

routes = web.RouteTableDef()

log = logging.getLogger(__name__)


@routes.get("/")
async def index(req: web.Request) -> web.Response:
    return web.Response(body=f"run-runner {os.environ['GIT_COMMIT']}")


@routes.route("OPTIONS", "/health_check")
async def healthcheck(req: web.Request) -> web.Response:
    return web.Response(status=404 if req.config_dict["runner"].busy else 200)


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

    runner = req.config_dict["runner"]
    if runner.busy:
        raise web.HTTPInternalServerError(reason="No free containers")

    compile_commands = []
    for compiler, compile_args in zip(
        data.get("compilers", ()), data.get("compile_args", ())
    ):
        compile_commands.append(f"{compiler} {compile_args}")

    return web.json_response(
        await runner.run_code(language, code, compile_commands, data["merge_output"])
    )
