import os
import uuid
import shlex
import shutil
import logging

from typing import Any, Dict, Union, Optional
from contextlib import suppress

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

CONTAINER_OUT_DIR = "/out"


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

    async def run_code(self, *args: Any, **kwargs: Any) -> _ResultType:
        self._running_containers += 1
        try:
            folder = await self._run_container(*args, **kwargs)

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
            self._running_containers -= 1
            log.debug("removing %s", folder)

            with suppress(FileNotFoundError):
                shutil.rmtree(folder)

        try:
            result["exit_code"] = int(result["exit_code"])
            result["exec_time"] = int(result["exec_time"]) / 1000
        except Exception:
            # in case user escapes entrypoint and messes with files
            for i in ("exit_code", "exec_time"):
                result[i] = DEFAULT_RESULTS[i]

        return result

    async def _run_container(
        self, language: str, code: str, compile_command: str, merge_output: bool
    ) -> str:
        with configure_scope() as scope:
            scope.set_tag("language", language)

            scope.set_extra("code", code[:8192])

        random_name = uuid.uuid1()

        new_local_folder = f"{self._local_folder}/{random_name}"
        new_host_folder = f"{self._host_folder}/{random_name}"

        image_name = f"iomirea/run-lang-{language}"

        os.makedirs(new_local_folder)
        try:
            input_filename = "to_compile" if compile_command else "input"
            with open(f"{new_local_folder}/{input_filename}", "w") as f:
                f.write(code)

            command = (
                f"docker run --rm --network none --cpus {self._max_cpu} "
                f"--memory {self._max_ram} --memory-swap {self._max_ram} "
                f"-v {new_host_folder}:{CONTAINER_OUT_DIR} "
                f"-v {new_host_folder}/{input_filename}:/{input_filename} "
                f"-e OUT_DIR={CONTAINER_OUT_DIR} "
            )

            if compile_command:
                command += f"-e COMPILE_COMMAND={shlex.quote(compile_command)} "

            if merge_output:
                command += "-e MERGE_OUTPUT=1 "

            command += image_name

            result = await run_shell_command(command, wait=True)
            if result.exit_code != 0:
                with configure_scope() as scope:
                    scope.set_extra("exit_code", result.exit_code)
                    scope.set_extra("stdout", result.stdout)
                    scope.set_extra("stderr", result.stderr)

                    log.error(f"error running container: {result}")

                raise web.HTTPInternalServerError(reason="Error running container")
        except Exception as e:
            log.exception(f"error processiong container: {e}")
        finally:
            return new_local_folder

    def calculate_optimal_container_count(self) -> int:
        # TODO

        return 6
