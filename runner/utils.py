import asyncio
import logging

from typing import Optional

log = logging.getLogger(__name__)


class ShellResult:
    def __init__(self, stdout: bytes, stderr: bytes, exit_code: int):
        self.stdout_bytes = stdout
        self.stderr_bytes = stderr

        self.exit_code = exit_code

        self._stdout: Optional[str] = None
        self._stderr: Optional[str] = None

    @property
    def stdout(self) -> str:
        if self._stdout is None:
            self._stdout = self.stdout_bytes.decode()

        return self._stdout

    @property
    def stderr(self) -> str:
        if self._stderr is None:
            self._stderr = self.stderr_bytes.decode()

        return self._stderr

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} exit_code={self.exit_code} stdout={self.stdout} stderr={self.stderr}>"


async def run_shell_command(command: str, wait: bool = False) -> ShellResult:
    log.debug("running shell command: %s", command)

    process = await asyncio.create_subprocess_shell(
        command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )

    if not wait:
        return ShellResult(b"", b"", -1)

    stdout, stderr = await process.communicate()

    return ShellResult(stdout, stderr, process.returncode)
