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

        self._bytes = {"stdout": b"", "stderr": b""}

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
            self._stdout = self._bytes["stdout"].decode(errors="replace")

        return self._stdout

    @property
    def stderr(self) -> str:
        if not self.exited:
            raise RuntimeError("Process is still running")

        if self._stderr is None:
            self._stderr = self._bytes["stderr"].decode(errors="replace")

        return self._stderr

    async def _wait(self, timeout: Optional[float]) -> None:
        await asyncio.wait_for(
            self._process.wait(), timeout=self._time_remaining(timeout)
        )

    # no longer needed
    async def read(
        self,
        limit: Optional[int] = None,
        *,
        timeout: Optional[float],
        input: Optional[bytes] = None,
        interval: float = 0.3,
        rate: float = 100,
        kill_after_limit: bool = True,
    ) -> None:

        stdin = self._process.stdin
        stdout = self._process.stdout
        stderr = self._process.stderr

        if stdout is None:
            raise RuntimeError("stdout reader is missing")

        if stderr is None:
            raise RuntimeError("stderr reader is missing")

        if stdin is not None:
            if input is not None:
                stdin.write(input)
                await stdin.drain()

            stdin.close()

        read_limit = DEFAULT_READ_LIMIT if limit is None else limit
        chunk_size = int(read_limit * interval / rate) or MIN_CHUNK_SIZE

        tasks: Dict[str, Optional[asyncio.Task[bytes]]] = {
            "stdout": None,
            "stderr": None,
        }

        async def read_task(stream: asyncio.StreamReader, name: str) -> None:
            nonlocal read_limit

            chunk = await stream.read(chunk_size)
            read_limit -= len(chunk)
            self._bytes[name] += chunk

            tasks[name] = None

        stream_pairs = list(zip(("stdout", "stderr"), (stdout, stderr)))
        try:
            while self._time_remaining(timeout) > 0 and read_limit > 0:
                for name, stream in stream_pairs:
                    if tasks[name] is None and not stream.at_eof():
                        tasks[name] = asyncio.create_task(read_task(stream, name))

                to_wait = [t for t in tasks.values() if t is not None]
                if not to_wait:
                    break

                done, pending = await asyncio.wait(
                    to_wait, timeout=interval, return_when=asyncio.FIRST_COMPLETED
                )

                if not done:
                    continue

            for task in pending:
                task.cancel()

            if read_limit <= 0:
                if kill_after_limit:
                    self._process.kill()
                else:
                    await self._wait(timeout)
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
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        stdin=asyncio.subprocess.PIPE if input is not None else None,
    )

    result = ShellResult(process)

    if not wait:
        return result

    kwargs = dict(timeout=timeout, input=input)

    if not read:
        kwargs["kill_after_limit"] = False

    await result.read(0 if not read else limit, **kwargs)  # type:ignore

    return result
