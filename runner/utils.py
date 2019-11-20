import time
import asyncio
import logging

from typing import Dict, Optional

log = logging.getLogger(__name__)

DEFAULT_READ_LIMIT = 1024 * 1024
MIN_CHUNK_SIZE = 100


class ShellResult:
    def __init__(self, process: asyncio.subprocess.Process, finally_kill: bool = True):
        self._process = process
        self._finally_kill = finally_kill

        self.stdout_bytes = b""
        self.stderr_bytes = b""

        self._stdout: Optional[str] = None
        self._stderr: Optional[str] = None

        self._start_time = time.time()

    def _time_remaining(self, timeout: Optional[float]) -> float:
        if timeout is None:
            return 1

        return timeout - (time.time() - self._start_time)

    @property
    def stdout(self) -> str:
        if not self.exited:
            raise RuntimeError("Process is still running")

        if self._stdout is None:
            self._stdout = self.stdout_bytes.decode()

        return self._stdout

    @property
    def stderr(self) -> str:
        if not self.exited:
            raise RuntimeError("Process is still running")

        if self._stderr is None:
            self._stderr = self.stderr_bytes.decode()

        return self._stderr

    async def _wait(self, timeout: Optional[float]) -> None:
        await asyncio.wait_for(
            self._process.wait(), timeout=self._time_remaining(timeout)
        )

    async def read(
        self,
        limit: Optional[int] = None,
        *,
        timeout: Optional[float],
        interval: float = 0.3,
        rate: float = 100,
        kill_after_limit: bool = True,
    ) -> None:
        try:
            stdout = self._process.stdout
            stderr = self._process.stderr

            if stdout is None:
                raise RuntimeError("stdout reader is missing")

            if stderr is None:
                raise RuntimeError("stderr reader is missing")

            limit = DEFAULT_READ_LIMIT if limit is None else limit
            chunk_size = int(limit * interval / rate) or MIN_CHUNK_SIZE

            tasks: Dict[str, Optional[asyncio.Task[bytes]]] = {
                "stdout": None,
                "stderr": None,
            }

            while (
                self._time_remaining(timeout) > 0
                and not (stdout.at_eof() and stderr.at_eof())
                and limit > 0
            ):
                if tasks["stdout"] is None and not stdout.at_eof():
                    tasks["stdout"] = asyncio.create_task(  # type: ignore
                        stdout.read(chunk_size), name="stdout"
                    )
                if tasks["stderr"] is None and not stderr.at_eof():
                    tasks["stderr"] = asyncio.create_task(  # type: ignore
                        stderr.read(chunk_size), name="stderr"
                    )

                to_wait = [t for t in tasks.values() if t is not None]

                done, pending = await asyncio.wait(
                    to_wait,
                    timeout=self._time_remaining(interval),
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if not done:
                    # timeout
                    continue

                for task in done:
                    name = task.get_name()  # type: ignore
                    chunk = task.result()

                    limit -= len(chunk)

                    if name == "stdout":
                        tasks["stdout"] = None
                        self.stdout_bytes += chunk
                    else:
                        tasks["stderr"] = None
                        self.stderr_bytes += chunk

            if limit <= 0:
                if kill_after_limit:
                    self._process.kill()
                else:
                    await self._wait(timeout)
        except ValueError:
            pass
        finally:
            for t in tasks.values():
                if t is not None:
                    t.cancel()

            if not self.exited:
                if self._finally_kill:
                    self._process.kill()

            await self._process.wait()

    @property
    def exited(self) -> bool:
        return self.exit_code is not None

    @property
    def exit_code(self) -> int:
        return self._process.returncode

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} exit_code={self.exit_code} stdout={self.stdout} stderr={self.stderr}>"


async def run_shell_command(
    command: str,
    input: Optional[bytes] = None,
    wait: bool = False,
    timeout: Optional[float] = None,
    limit: Optional[int] = None,
    read: bool = True,
) -> ShellResult:
    # TODO: input processing
    log.debug("running shell command: %s", command)

    process = await asyncio.create_subprocess_shell(
        command,
        # stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    result = ShellResult(process)

    if not wait:
        return result

    kwargs = dict(timeout=timeout)

    if not read:
        kwargs["kill_after_limit"] = False

    await result.read(0 if not read else limit, **kwargs)  # type: ignore

    return result
