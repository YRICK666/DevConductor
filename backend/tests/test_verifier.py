from __future__ import annotations

import sys
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.execution import CommandRunner, CommandRunnerError
from backend.app.schemas.command import CommandResult, VerificationResult
from backend.app.schemas.verification import VerificationSpec, VerificationSummary
from backend.app.verifier import Verifier


def started_at() -> datetime:
    return datetime(2026, 6, 12, 12, 0, tzinfo=UTC)


def command_result(
    *,
    command: list[str] | None = None,
    exit_code: int | None = 0,
    timed_out: bool = False,
) -> CommandResult:
    start = started_at()
    return CommandResult(
        command=command or ["python", "-m", "pytest"],
        exit_code=exit_code,
        stdout="",
        stderr="",
        started_at=start,
        finished_at=start + timedelta(seconds=1),
        timed_out=timed_out,
    )


def spec(
    name: str = "pytest",
    *,
    command: list[str] | None = None,
    timeout_seconds: float | None = None,
    env: dict[str, str] | None = None,
    required: bool = True,
) -> VerificationSpec:
    return VerificationSpec(
        name=name,
        command=["python", "-m", "pytest"] if command is None else command,
        timeout_seconds=timeout_seconds,
        env=env or {},
        required=required,
    )


class FakeCommandRunner:
    def __init__(
        self,
        outcomes: list[CommandResult | CommandRunnerError],
    ) -> None:
        self._outcomes = list(outcomes)
        self.calls: list[tuple[list[str], Path, float | None, dict[str, str] | None]] = []

    async def run(
        self,
        command: list[str],
        *,
        cwd: Path,
        timeout_seconds: float | None = None,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        self.calls.append((list(command), cwd, timeout_seconds, dict(env) if env else None))
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, CommandRunnerError):
            raise outcome
        return outcome


@pytest.mark.asyncio
async def test_single_success_verification_passes(tmp_path: Path) -> None:
    runner = FakeCommandRunner([command_result(exit_code=0)])
    summary = await Verifier(runner).verify([spec()], cwd=tmp_path)

    assert summary.passed is True
    assert summary.results[0].passed is True
    assert summary.results[0].details == "Command completed successfully."


@pytest.mark.asyncio
async def test_non_zero_exit_code_fails(tmp_path: Path) -> None:
    runner = FakeCommandRunner([command_result(exit_code=2)])
    summary = await Verifier(runner).verify([spec()], cwd=tmp_path)

    assert summary.passed is False
    assert summary.results[0].passed is False
    assert summary.results[0].details == "Command exited with code 2."


@pytest.mark.asyncio
async def test_timeout_result_fails(tmp_path: Path) -> None:
    runner = FakeCommandRunner([command_result(exit_code=None, timed_out=True)])
    summary = await Verifier(runner).verify([spec()], cwd=tmp_path)

    assert summary.passed is False
    assert summary.results[0].passed is False
    assert summary.results[0].details == "Command timed out."


@pytest.mark.asyncio
async def test_none_exit_code_fails(tmp_path: Path) -> None:
    runner = FakeCommandRunner([command_result(exit_code=None)])
    summary = await Verifier(runner).verify([spec()], cwd=tmp_path)

    assert summary.passed is False
    assert summary.results[0].passed is False


@pytest.mark.asyncio
async def test_multiple_verifications_run_in_input_order(tmp_path: Path) -> None:
    runner = FakeCommandRunner([command_result(exit_code=0), command_result(exit_code=0)])
    specs = [spec("first", command=["first"]), spec("second", command=["second"])]

    summary = await Verifier(runner).verify(specs, cwd=tmp_path)

    assert [result.name for result in summary.results] == ["first", "second"]
    assert [call[0] for call in runner.calls] == [["first"], ["second"]]


@pytest.mark.asyncio
async def test_stop_on_failure_false_continues_after_failure(tmp_path: Path) -> None:
    runner = FakeCommandRunner([command_result(exit_code=1), command_result(exit_code=0)])
    summary = await Verifier(runner).verify(
        [spec("fail"), spec("later")],
        cwd=tmp_path,
        stop_on_failure=False,
    )

    assert [result.name for result in summary.results] == ["fail", "later"]
    assert summary.stopped_early is False


@pytest.mark.asyncio
async def test_stop_on_failure_true_stops_after_required_failure(tmp_path: Path) -> None:
    runner = FakeCommandRunner([command_result(exit_code=1), command_result(exit_code=0)])
    summary = await Verifier(runner).verify(
        [spec("fail"), spec("not-run")],
        cwd=tmp_path,
        stop_on_failure=True,
    )

    assert [result.name for result in summary.results] == ["fail"]
    assert len(runner.calls) == 1
    assert summary.stopped_early is True


@pytest.mark.asyncio
async def test_optional_failure_does_not_stop_early(tmp_path: Path) -> None:
    runner = FakeCommandRunner([command_result(exit_code=1), command_result(exit_code=0)])
    summary = await Verifier(runner).verify(
        [spec("optional", required=False), spec("required")],
        cwd=tmp_path,
        stop_on_failure=True,
    )

    assert [result.name for result in summary.results] == ["optional", "required"]
    assert summary.stopped_early is False


@pytest.mark.asyncio
async def test_optional_failure_keeps_required_passed_true(tmp_path: Path) -> None:
    runner = FakeCommandRunner([command_result(exit_code=1), command_result(exit_code=0)])
    summary = await Verifier(runner).verify(
        [spec("optional", required=False), spec("required")],
        cwd=tmp_path,
    )

    assert summary.required_passed is True
    assert summary.passed is True
    assert summary.failed_count == 1


@pytest.mark.asyncio
async def test_all_required_verifications_passing_makes_summary_pass(tmp_path: Path) -> None:
    runner = FakeCommandRunner([command_result(exit_code=0), command_result(exit_code=0)])
    summary = await Verifier(runner).verify([spec("one"), spec("two")], cwd=tmp_path)

    assert summary.passed is True
    assert summary.required_passed is True


@pytest.mark.asyncio
async def test_required_failure_makes_summary_fail(tmp_path: Path) -> None:
    runner = FakeCommandRunner([command_result(exit_code=0), command_result(exit_code=1)])
    summary = await Verifier(runner).verify([spec("one"), spec("two")], cwd=tmp_path)

    assert summary.passed is False
    assert summary.required_passed is False


@pytest.mark.asyncio
async def test_empty_verification_list_returns_passing_empty_summary(tmp_path: Path) -> None:
    runner = FakeCommandRunner([])
    summary = await Verifier(runner).verify([], cwd=tmp_path)

    assert summary.passed is True
    assert summary.required_passed is True
    assert summary.total_count == 0
    assert summary.results == []


@pytest.mark.asyncio
async def test_command_runner_error_becomes_structured_failure(tmp_path: Path) -> None:
    runner = FakeCommandRunner([CommandRunnerError("Executable not found: 'missing'")])
    summary = await Verifier(runner).verify([spec("missing")], cwd=tmp_path)

    result = summary.results[0]
    assert result.name == "missing"
    assert result.command_result is None
    assert result.passed is False
    assert result.details == "Command could not be started: Executable not found: 'missing'"


@pytest.mark.asyncio
async def test_start_failure_preserves_previous_results(tmp_path: Path) -> None:
    runner = FakeCommandRunner(
        [command_result(exit_code=0), CommandRunnerError("Unable to start command: 'bad'")]
    )
    summary = await Verifier(runner).verify([spec("ok"), spec("bad")], cwd=tmp_path)

    assert [result.name for result in summary.results] == ["ok", "bad"]
    assert summary.results[0].passed is True
    assert summary.results[1].command_result is None


def test_verification_spec_rejects_blank_name() -> None:
    with pytest.raises(ValidationError):
        spec(name="   ")


def test_verification_spec_rejects_empty_command() -> None:
    with pytest.raises(ValidationError):
        spec(command=[])


def test_verification_spec_rejects_blank_command_argument() -> None:
    with pytest.raises(ValidationError):
        spec(command=["python", "   "])


def test_verification_spec_rejects_invalid_timeout() -> None:
    with pytest.raises(ValidationError):
        spec(timeout_seconds=0)


def test_verification_spec_env_defaults_are_not_shared() -> None:
    first = spec("first")
    second = spec("second")

    first.env["DEVCONDUCTOR_TEST"] = "value"

    assert second.env == {}


@pytest.mark.asyncio
async def test_input_specs_are_not_modified(tmp_path: Path) -> None:
    runner = FakeCommandRunner([command_result(exit_code=0)])
    specs = [spec("one", command=["python", "-c", "pass"], env={"VALUE": "one"})]
    original = [item.model_dump() for item in specs]

    await Verifier(runner).verify(specs, cwd=tmp_path)

    assert [item.model_dump() for item in specs] == original


@pytest.mark.asyncio
async def test_input_command_list_is_not_modified(tmp_path: Path) -> None:
    runner = FakeCommandRunner([command_result(exit_code=0)])
    command = ["python", "-c", "pass"]
    verification = spec("one", command=command)

    await Verifier(runner).verify([verification], cwd=tmp_path)

    assert command == ["python", "-c", "pass"]
    assert verification.command == ["python", "-c", "pass"]


@pytest.mark.asyncio
async def test_input_env_mapping_is_not_modified(tmp_path: Path) -> None:
    runner = FakeCommandRunner([command_result(exit_code=0)])
    env = {"VALUE": "one"}
    verification = spec("one", env=env)

    await Verifier(runner).verify([verification], cwd=tmp_path)

    assert env == {"VALUE": "one"}
    assert verification.env == {"VALUE": "one"}


@pytest.mark.asyncio
async def test_cwd_is_passed_to_command_runner(tmp_path: Path) -> None:
    runner = FakeCommandRunner([command_result(exit_code=0)])

    await Verifier(runner).verify([spec()], cwd=tmp_path)

    assert runner.calls[0][1] == tmp_path


@pytest.mark.asyncio
async def test_timeout_is_passed_to_command_runner(tmp_path: Path) -> None:
    runner = FakeCommandRunner([command_result(exit_code=0)])

    await Verifier(runner).verify([spec(timeout_seconds=2.5)], cwd=tmp_path)

    assert runner.calls[0][2] == 2.5


@pytest.mark.asyncio
async def test_env_is_passed_to_command_runner(tmp_path: Path) -> None:
    runner = FakeCommandRunner([command_result(exit_code=0)])

    await Verifier(runner).verify([spec(env={"VALUE": "one"})], cwd=tmp_path)

    assert runner.calls[0][3] == {"VALUE": "one"}


def test_summary_counts_are_accurate() -> None:
    results = [
        VerificationResult(
            name="one",
            command_result=command_result(exit_code=0),
            passed=True,
            required=True,
        ),
        VerificationResult(
            name="two",
            command_result=command_result(exit_code=1),
            passed=False,
            required=True,
        ),
        VerificationResult(
            name="three",
            command_result=command_result(exit_code=1),
            passed=False,
            required=False,
        ),
    ]
    summary = VerificationSummary.from_results(results)

    assert summary.total_count == 3
    assert summary.passed_count == 1
    assert summary.failed_count == 2


def test_timed_out_count_is_accurate() -> None:
    results = [
        VerificationResult(
            name="one",
            command_result=command_result(exit_code=0),
            passed=True,
            required=True,
        ),
        VerificationResult(
            name="two",
            command_result=command_result(exit_code=None, timed_out=True),
            passed=False,
            required=True,
        ),
    ]
    summary = VerificationSummary.from_results(results)

    assert summary.timed_out_count == 1


def test_verification_summary_json_round_trip() -> None:
    summary = VerificationSummary.from_results(
        [
            VerificationResult(
                name="pytest",
                command_result=command_result(exit_code=0),
                passed=True,
                required=True,
            )
        ]
    )

    loaded = VerificationSummary.model_validate_json(summary.model_dump_json())

    assert loaded == summary


def test_verification_spec_rejects_unknown_top_level_field() -> None:
    with pytest.raises(ValidationError):
        VerificationSpec.model_validate({"name": "pytest", "command": ["pytest"], "model": "x"})


def test_summary_rejects_inconsistent_counts() -> None:
    with pytest.raises(ValidationError):
        VerificationSummary.model_validate(
            {
                "results": [
                    VerificationResult(
                        name="pytest",
                        command_result=command_result(exit_code=0),
                        passed=True,
                        required=True,
                    )
                ],
                "total_count": 2,
            }
        )


@pytest.mark.asyncio
async def test_real_runner_works_in_windows_chinese_path_with_spaces(tmp_path: Path) -> None:
    cwd = tmp_path / "课程 资料"
    cwd.mkdir()
    command = [sys.executable, "-c", "import pathlib; print(pathlib.Path.cwd().name)"]

    summary = await Verifier(CommandRunner()).verify(
        [spec("cwd", command=command)],
        cwd=cwd,
    )

    assert summary.passed is True
    assert summary.results[0].command_result is not None
    assert summary.results[0].command_result.stdout.splitlines() == ["课程 资料"]


@pytest.mark.asyncio
async def test_real_command_runner_success_command_passes(tmp_path: Path) -> None:
    summary = await Verifier(CommandRunner()).verify(
        [spec("success", command=[sys.executable, "-c", "print('ok')"])],
        cwd=tmp_path,
    )

    assert summary.passed is True
    assert summary.results[0].passed is True


@pytest.mark.asyncio
async def test_real_command_runner_failure_command_fails(tmp_path: Path) -> None:
    summary = await Verifier(CommandRunner()).verify(
        [spec("failure", command=[sys.executable, "-c", "raise SystemExit(3)"])],
        cwd=tmp_path,
    )

    assert summary.passed is False
    assert summary.results[0].passed is False
    assert summary.results[0].details == "Command exited with code 3."
