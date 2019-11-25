import logging

from typing import Any, Dict, List, Union, Mapping, Optional
from datetime import datetime

import aiohttp

from aiohttp import web
from sentry_sdk import push_scope, configure_scope

log = logging.getLogger(__name__)

_ResultType = Dict[str, Union[str, int, float]]

DOCKER_API_VERSION = "1.40"

CPU_QUOTA = 100000

OUTPUT_LIMIT = 1024 * 1024

EXEC_TIMEOUT = 30
CONTAINER_TIMEOUT = EXEC_TIMEOUT + 2


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
        self._session = aiohttp.ClientSession(
            connector=aiohttp.UnixConnector(path=self._socket)
        )

    async def docker_request(
        self,
        method: str = "GET",
        path: str = "",
        params: Mapping[str, Any] = {},
        body: Any = None,
        stream: bool = False,
    ) -> Any:
        url = f"{self._url_base}/{path}"
        log.debug("%6s: %s", method, url)

        async with self._session.request(method, url, params=params, json=body) as resp:
            if resp.status // 100 not in (2, 3):
                json = await resp.json()
                with push_scope() as scope:
                    scope.set_extra("request", body)
                    scope.set_extra("response", json)

                log.error(f"{url}: {resp.status} ({json['message']})")

                raise web.HTTPInternalServerError(reason="Docker API error")

            if stream:
                stdout = b""
                stderr = b""

                header_size = 8

                bytes_read = 0

                try:
                    while bytes_read < EXEC_TIMEOUT and not resp.content.at_eof():
                        header = await resp.content.readexactly(header_size)

                        chunk_length = int.from_bytes(header[3:], byteorder="big")
                        chunk = await resp.content.read(chunk_length)

                        chunk_type = header[0]
                        if chunk_type == 1:  # stdout
                            stdout += chunk
                        elif chunk_type == 2:  # stderr
                            stderr += chunk

                        bytes_read += chunk_length + header_size
                finally:
                    return stdout, stderr

            if resp.status == 204:
                json = {}
            else:
                json = await resp.json()

            warnings = json.get("Warnings")
            if warnings:
                log.warn(f"docker warning(s): {warnings}")

            return json

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

        env = [f"CODE={code}", f"TIMEOUT={EXEC_TIMEOUT}"]
        if compile_commands:
            env.append(f"COMPILE_COMMAND={' && '.join(compile_commands)}")

        if input is not None:
            if not input.endswith("\n"):
                input += "\n"
            env.append(f"INPUT={input}")

        if merge_output:
            env.append("MERGE_OUTPUT=1")

        try:
            create_result = await self.docker_request(
                "POST",
                "containers/create",
                body={
                    "Env": env,
                    "Image": f"iomirea/run-lang-{language}",
                    "StopTimeout": CONTAINER_TIMEOUT,
                    "WorkingDir": "/sandbox",
                    "AutoRemove": False,
                    "NetworkMode": "none",
                    "NetworkDisabled": True,
                    "HealthCheck": {"Test": ("NONE",)},
                    "HostConfig": {
                        "Memory": self._max_ram,
                        "MemorySwap": self._max_ram,
                        "CpuQuota": CPU_QUOTA,
                        "CpuPeriod": int(self._max_cpu * CPU_QUOTA),
                    },
                },
            )
            new_id = create_result["Id"]
            log.debug("created %s", new_id)

            await self.docker_request("POST", f"containers/{new_id}/start")

            stdout, stderr = await self.docker_request(
                "POST",
                f"containers/{new_id}/attach",
                {"logs": 1, "stream": 1, "stdin": 1, "stdout": 1, "stderr": 1},
                stream=True,
            )

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
                stdout=stdout.decode(errors="ignore"),
                stderr=stderr.decode(errors="ignore"),
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
