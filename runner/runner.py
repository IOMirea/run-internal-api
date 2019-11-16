import os
import shlex
import shutil
import logging

from typing import Dict, Union, Optional

from aiohttp import web
from sentry_sdk import configure_scope

from .utils import run_shell_command

log = logging.getLogger(__name__)

_ResultType = Dict[str, Union[str, int, float]]

FILE_SIZE_LIMIT = 1024 * 1024 // 2  # 0.5m, hardcoded for now

DEFAULT_RESULTS: _ResultType = {
    "exit_code": -1000,
    "stdout": "",
    "stderr": "",
    "exec_time": 0.0,
}


class DockerRunner:
    def __init__(
        self,
        max_ram: str,
        max_cpu: float,
        local_folder: str,
        host_folder: str,
        max_containers: Optional[int] = None,
    ):
        self._max_ram = max_ram
        self._max_cpu = max_cpu
        self._local_folder = local_folder
        self._host_folder = host_folder

        self._max_containers = (
            self.calculate_optimal_container_count()
            if max_containers is None
            else max_containers
        )

        self._running_containers = 0

    @property
    def busy(self) -> bool:
        return self._running_containers >= self._max_containers

    async def run_code(self, language: str, code: str) -> _ResultType:
        self._running_containers += 1
        try:
            shell_result = await run_shell_command(
                f"run_container.sh {language} {self._local_folder} {self._host_folder} "
                f"                 {self._max_ram} {self._max_cpu} {shlex.quote(code)}",
                wait=True,
            )
        finally:
            self._running_containers -= 1

        folder = shell_result.stdout.split("\n")[0]
        try:
            if shell_result.exit_code != 0:
                with configure_scope() as scope:
                    scope.set_tag("language", language)

                    scope.set_extra("code", code[:8192])

                    scope.set_extra("exit_code", shell_result.exit_code)
                    scope.set_extra("stdout", shell_result.stdout)
                    scope.set_extra("stderr", shell_result.stderr)

                log.error(f"Error running container: {shell_result}")

                raise web.HTTPInternalServerError(reason="Error running container")

            result: _ResultType = {}
            for name in DEFAULT_RESULTS.keys():
                file_name = f"{folder}/{name}"
                try:
                    file_size = os.path.getsize(file_name)
                except OSError:
                    # in case user escapes entrypoint and messes with files or they
                    # aren't written for other reason
                    result[name] = DEFAULT_RESULTS[name]

                    continue

                with open(file_name, "rb") as f:
                    if file_size > FILE_SIZE_LIMIT:
                        f.seek(file_size - FILE_SIZE_LIMIT)

                    result[name] = f.read().decode(errors="ignore")

        finally:
            log.debug("removing %s", folder)

            shutil.rmtree(folder)

        try:
            result["exit_code"] = int(result["exit_code"])
            result["exec_time"] = int(result["exec_time"]) / 1000
        except Exception:
            # in case user escapes entrypoint and messes with files
            for i in ("exit_code", "exec_time"):
                result[i] = DEFAULT_RESULTS[i]

        return result

    def calculate_optimal_container_count(self) -> int:
        # TODO

        return 6
