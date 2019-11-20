import uuid
import shlex
import logging

from typing import Any, Dict, Union, Optional
from datetime import datetime

from aiohttp import web
from sentry_sdk import configure_scope

from .utils import ShellResult, run_shell_command

log = logging.getLogger(__name__)

_ResultType = Dict[str, Union[str, int, float]]

OUTPUT_LEN_LIMIT = 1024 * 1024 / 2

DOCKER_RUN_EXIT_CODES = {125, 126, 127}


class DockerRunner:
    def __init__(
        self, max_ram: str, max_cpu: float, max_containers: Optional[int] = None
    ):
        self._max_ram = max_ram
        self._max_cpu = max_cpu

        self._max_containers = (
            self.calculate_optimal_container_count()
            if max_containers is None
            else max_containers
        )

        self._running_containers = 0

    @property
    def busy(self) -> bool:
        return self._running_containers >= self._max_containers

    async def run_code(self, *args: Any, **kwargs: Any) -> _ResultType:
        self._running_containers += 1
        try:
            return await self._run_container(*args, **kwargs)
        finally:
            self._running_containers -= 1

    async def _run_container(
        self, language: str, code: str, compile_command: str, merge_output: bool
    ) -> _ResultType:
        with configure_scope() as scope:
            scope.set_tag("language", language)

            scope.set_extra("code", code[:8192])

        random_name = uuid.uuid1()

        workdir = "/sandbox"

        image_name = f"iomirea/run-lang-{language}"

        try:
            command = (
                f"docker create --name {random_name} --workdir {workdir} "
                f"--log-driver none --network none "
                f"--cpus {self._max_cpu} -e INPUT={shlex.quote(code)} "
                f"--memory {self._max_ram} --memory-swap {self._max_ram} "
            )

            if compile_command:
                command += f"-e COMPILE_COMMAND={shlex.quote(compile_command)} "

            if merge_output:
                command += "-e MERGE_OUTPUT=1 "

            command += image_name

            def check_result(
                result: ShellResult, action: str, docker_run: bool = False
            ) -> None:
                if docker_run:
                    if result.exit_code not in DOCKER_RUN_EXIT_CODES:
                        return
                else:
                    if result.exit_code == 0:
                        return

                with configure_scope() as scope:
                    scope.set_extra("exit_code", result.exit_code)
                    scope.set_extra("stdout", result.stdout[:1024])
                    scope.set_extra("stderr", result.stderr[:1024])

                log.error(result)

                raise web.HTTPInternalServerError(reason=f"Error {action} container")

            create_result = await run_shell_command(command, wait=True)
            check_result(create_result, "creating")

            run_result = await run_shell_command(
                f"docker start --attach {random_name}", wait=True
            )
            check_result(run_result, "running", docker_run=True)

            inspect_format = (
                "{{.State.ExitCode}};{{.State.StartedAt}};{{.State.FinishedAt}};"
            )
            inspect_result = await run_shell_command(
                f"docker inspect {random_name} --format='{inspect_format}'", wait=True
            )
            check_result(inspect_result, "inspecting")

            exit_code, started_at, finished_at, _ = inspect_result.stdout.split(";")

            def parse_datetime_ns(inp: str) -> float:
                """Converts iso formatted string with nanoseconds precision to float."""

                dot_index = inp.rindex(".")
                datetime_no_ms = inp[:dot_index]
                ms_and_ns = float(inp[dot_index:-1])

                return datetime.fromisoformat(datetime_no_ms).timestamp() + ms_and_ns

            exec_time = parse_datetime_ns(finished_at) - parse_datetime_ns(started_at)

            return dict(
                stdout=run_result.stdout,
                stderr=run_result.stderr,
                exit_code=exit_code,
                exec_time=exec_time,
            )
        finally:
            await run_shell_command(f"docker rm -vf {random_name}", read=False)

    def calculate_optimal_container_count(self) -> int:
        # TODO

        return 6
