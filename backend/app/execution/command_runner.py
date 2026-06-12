"""Async local command execution with structured results."""

import asyncio
import os
from collections.abc import Mapping
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

from backend.app.execution.exceptions import CommandRunnerError
from backend.app.schemas.command import CommandResult


class CommandRunner:
    """Run local commands without invoking a shell."""

    async def run(
        self,
        command: list[str],
        *,
        cwd: Path,
        timeout_seconds: float | None = None,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        """Execute a local process and return captured execution facts."""

        self._validate_cwd(cwd)
        self._validate_command(command)
        command_args = list(command)
        process_env = os.environ.copy()
        if env is not None:
            process_env.update(dict(env))

        started_at = datetime.now(UTC)
        try:
            process = await asyncio.create_subprocess_exec(
                *command_args,
                cwd=cwd,
                env=process_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise CommandRunnerError(f"Executable not found: {command_args[0]!r}") from exc
        except PermissionError as exc:
            message = f"Permission denied while starting: {command_args[0]!r}"
            raise CommandRunnerError(message) from exc
        except OSError as exc:
            raise CommandRunnerError(f"Unable to start command: {command_args[0]!r}") from exc

        timed_out = False
        exit_code: int | None
        communicate_task = asyncio.create_task(process.communicate())
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                asyncio.shield(communicate_task),
                timeout=timeout_seconds,
            )
            exit_code = process.returncode
        except TimeoutError:
            timed_out = True
            stdout_bytes, stderr_bytes = await self._terminate_process(process, communicate_task)
            exit_code = None

        finished_at = datetime.now(UTC)
        return CommandResult(
            command=command_args,
            exit_code=exit_code,
            stdout=self._decode_output(stdout_bytes),
            stderr=self._decode_output(stderr_bytes),
            started_at=started_at,
            finished_at=finished_at,
            timed_out=timed_out,
        )

    @staticmethod
    def _validate_cwd(cwd: Path) -> None:
        if not cwd.exists():
            raise CommandRunnerError(f"Working directory does not exist: {cwd}")
        if not cwd.is_dir():
            raise CommandRunnerError(f"Working directory is not a directory: {cwd}")

    @staticmethod
    def _validate_command(command: list[str]) -> None:
        if not command:
            raise CommandRunnerError("Command must contain at least one argument")
        for argument in command:
            if not argument.strip():
                raise CommandRunnerError("Command arguments must not be blank")

    @staticmethod
    async def _terminate_process(
        process: asyncio.subprocess.Process,
        communicate_task: asyncio.Task[tuple[bytes, bytes]],
    ) -> tuple[bytes, bytes]:
        if process.returncode is None:
            with suppress(ProcessLookupError):
                process.kill()
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(communicate_task, timeout=5)
        except TimeoutError:
            stdout_bytes, stderr_bytes = b"", b""
        return stdout_bytes, stderr_bytes

    @staticmethod
    def _decode_output(output: bytes) -> str:
        return output.decode("utf-8", errors="replace")
