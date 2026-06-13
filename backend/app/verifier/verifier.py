"""Deterministic verification orchestration."""

from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

from backend.app.execution import CommandRunner
from backend.app.execution.exceptions import CommandRunnerError
from backend.app.schemas.command import CommandResult, VerificationResult
from backend.app.schemas.verification import VerificationSpec, VerificationSummary


class _CommandRunner(Protocol):
    async def run(
        self,
        command: list[str],
        *,
        cwd: Path,
        timeout_seconds: float | None = None,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult: ...


class Verifier:
    """Run deterministic verification commands through a CommandRunner."""

    def __init__(self, command_runner: _CommandRunner | None = None) -> None:
        self._command_runner = command_runner or CommandRunner()

    async def verify(
        self,
        specs: list[VerificationSpec],
        *,
        cwd: Path,
        stop_on_failure: bool = False,
    ) -> VerificationSummary:
        """Run verification specs in order.

        An empty spec list returns an empty passing summary.
        """

        results: list[VerificationResult] = []
        stopped_early = False

        for spec in specs:
            result = await self._run_one(spec, cwd=cwd)
            results.append(result)

            if stop_on_failure and spec.required and not result.passed:
                stopped_early = True
                break

        return VerificationSummary.from_results(results, stopped_early=stopped_early)

    async def _run_one(self, spec: VerificationSpec, *, cwd: Path) -> VerificationResult:
        command = list(spec.command)
        env = dict(spec.env)

        try:
            command_result = await self._command_runner.run(
                command,
                cwd=cwd,
                timeout_seconds=spec.timeout_seconds,
                env=env,
            )
        except CommandRunnerError as exc:
            return VerificationResult(
                name=spec.name,
                command_result=None,
                passed=False,
                required=spec.required,
                details=f"Command could not be started: {exc}",
            )

        passed = command_result.exit_code == 0 and not command_result.timed_out
        return VerificationResult(
            name=spec.name,
            command_result=command_result,
            passed=passed,
            required=spec.required,
            details=self._details_for(command_result),
        )

    @staticmethod
    def _details_for(command_result: CommandResult) -> str:
        if command_result.timed_out:
            return "Command timed out."
        if command_result.exit_code == 0:
            return "Command completed successfully."
        return f"Command exited with code {command_result.exit_code}."
