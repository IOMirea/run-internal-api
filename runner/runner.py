import uuid
import logging

from typing import Any, Dict, List, Union, Mapping, Optional
from datetime import datetime

import aiohttp

from aiohttp import web
from sentry_sdk import push_scope, configure_scope

from .utils import ShellResult, run_shell_command

log = logging.getLogger(__name__)

_ResultType = Dict[str, Union[str, int, float]]

OUTPUT_LEN_LIMIT = 1024 * 1024 / 2

DOCKER_API_VERSION = "1.40"

CPU_QUOTA = 100000

# TODO: dlete after replacing run call
DOCKER_RUN_EXIT_CODES = {125, 126, 127}


async def setup(app: web.Application) -> None:
    config = app["config"]

    # TODO: docker username, password
    runner = DockerRunner(
        config["docker"]["socket"],
        config["app"]["max-container-ram"],
        config["app"]["max-container-cpu"],
        config["app"]["max-containers"],
    )
    await runner.setup()

    app["runner"] = runner


def dumb_megabytes_to_bytes(mb: str) -> int:
    if mb.lower().endswith("m"):
        mb = mb[:-1]
    return int(mb) // (1024 * 1024)


class DockerRunner:
    def __init__(
        self,
        socket_path: str,
        max_ram: str,
        max_cpu: float,
        max_containers: Optional[int] = None,
    ):
        self._socket = socket_path
        self._url_base = f"unix://{DOCKER_API_VERSION}"
        self._max_ram = dumb_megabytes_to_bytes(max_ram)
        self._max_cpu = max_cpu

        self._max_containers = (
            self.calculate_optimal_container_count()
            if max_containers is None
            else max_containers
        )

        self._running_containers = 0

        self._session: aiohttp.ClientSession

    async def setup(self) -> None:
        connector = aiohttp.UnixConnector(path=self._socket)
        self._session = aiohttp.ClientSession(connector=connector)

    async def docker_request(
        self,
        method: str,
        path: str,
        params: Optional[Mapping[str, Any]] = None,
        body: Any = None,
    ) -> Any:
        url = f"{self._url_base}/{path}"
        log.debug("%6s: %s", method, url)
        async with self._session.request(method, url, params=params, json=body) as req:
            if req.status == 204:
                body = {}
            else:
                body = await req.json()

            if req.status // 100 != 2:
                with push_scope() as scope:
                    scope.set_extra("body", body)

                log.error(f"{url}: {req.status} ({body['message']})")

                raise web.HTTPInternalServerError(reason="Docker error")

            warnings = body.get("Warnings")
            if warnings:
                log.warn(f"docker warning(s): {warnings}")

            return body

    @property
    def busy(self) -> bool:
        return self._running_containers >= self._max_containers

    async def run_code(self, *args: Any, **kwargs: Any) -> _ResultType:
        if self.busy:
            raise web.HTTPServiceUnavailable(
                reason="No free containers. Try again later"
            )

        self._running_containers += 1
        try:
            return await self._run_container(*args, **kwargs)
        finally:
            self._running_containers -= 1

    async def _run_container(
        self,
        language: str,
        code: str,
        input: Optional[str],
        compile_commands: List[str],
        merge_output: bool,
    ) -> _ResultType:
        with configure_scope() as scope:
            scope.set_tag("language", language)

            scope.set_extra("code", code[:8192])

        random_name = uuid.uuid1().hex

        workdir = "/sandbox"

        image_name = f"iomirea/run-lang-{language}"

        env = [f"INPUT={code}"]
        if compile_commands:
            env.append(f"COMPILE_COMMAND={' && '.join(compile_commands)}")
        if merge_output:
            env.append("MERGE_OUTPUT=1")

        try:
            create_result = await self.docker_request(
                "POST",
                "containers/create",
                {"name": random_name},
                {
                    "Env": env,
                    "Image": image_name,
                    "StopTimeout": 40,
                    "WorkDir": workdir,
                    "AutoRemove": False,
                    "OpenStdin": True,
                    "StdinOnce": True,
                    "NetworkMode": "none",
                    "NetworkDisabled": True,
                    "HealthCheck": {"Test": ("NONE",)},
                    "HostConfig": {
                        "LogConfig": {"Type": "none"},
                        "Memory": self._max_ram,
                        "MemorySwap": self._max_ram,
                        "CpuQuota": CPU_QUOTA,
                        "CpuPeriod": int(self._max_cpu * CPU_QUOTA),
                    },
                },
            )
            new_id = create_result["Id"]
            log.debug("created container %s", new_id)

            def check_result(
                result: ShellResult, action: str, docker_run: bool = False
            ) -> None:
                if docker_run:
                    if result.exit_code not in DOCKER_RUN_EXIT_CODES:
                        return
                else:
                    if result.exit_code == 0:
                        return

                with push_scope() as scope:
                    scope.set_extra("exit_code", result.exit_code)
                    scope.set_extra("stdout", result.stdout)
                    scope.set_extra("stderr", result.stderr)
                    scope.set_extra("input", input)

                log.error(result)

                raise web.HTTPInternalServerError(reason=f"Error {action} container")

            if input is None:
                stdin = None
            else:
                if not input.endswith("\n"):
                    input += "\n"
                stdin = input.encode(errors="replace")

            run_result = await run_shell_command(
                f"docker start --attach --interactive {random_name}",
                wait=True,
                input=stdin,
            )
            check_result(run_result, "running", docker_run=True)

            inspect_result = await self.docker_request(
                "GET", f"containers/{new_id}/json"
            )
            state = inspect_result["State"]
            started_at = state["StartedAt"]
            finished_at = state["FinishedAt"]

            def parse_datetime_ns(inp: str) -> float:
                """Converts iso formatted string with nanoseconds precision to float."""

                dot_index = inp.rindex(".")
                datetime_no_ms = inp[:dot_index]
                ms_and_ns = float(inp[dot_index:-1])

                return datetime.fromisoformat(datetime_no_ms).timestamp() + ms_and_ns

            if finished_at == "0001-01-01T00:00:00Z":  # killed, no timestamp set
                exec_time = -1.0
            else:
                exec_time = parse_datetime_ns(finished_at) - parse_datetime_ns(
                    started_at
                )

            return dict(
                stdout=run_result.stdout,
                stderr=run_result.stderr,
                exit_code=state["ExitCode"],
                exec_time=exec_time,
            )
        finally:
            await self.docker_request(
                "DELETE", f"containers/{new_id}", {"v": 1, "force": 1}
            )

    def calculate_optimal_container_count(self) -> int:
        # TODO

        return 6
