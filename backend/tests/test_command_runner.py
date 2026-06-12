from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Mapping
from pathlib import Path

import pytest

from backend.app.execution import CommandRunner, CommandRunnerError
from backend.app.schemas.command import CommandResult


@pytest.fixture
def runner() -> CommandRunner:
    return CommandRunner()


def python_command(code: str) -> list[str]:
    return [sys.executable, "-c", code]


@pytest.mark.asyncio
async def test_success_returns_zero_exit_code(runner: CommandRunner, tmp_path: Path) -> None:
    result = await runner.run(python_command("pass"), cwd=tmp_path)

    assert result.exit_code == 0
    assert result.timed_out is False


@pytest.mark.asyncio
async def test_captures_stdout(runner: CommandRunner, tmp_path: Path) -> None:
    result = await runner.run(python_command("print('hello stdout')"), cwd=tmp_path)

    assert result.stdout.splitlines() == ["hello stdout"]


@pytest.mark.asyncio
async def test_captures_stderr(runner: CommandRunner, tmp_path: Path) -> None:
    result = await runner.run(
        python_command("import sys; print('hello stderr', file=sys.stderr)"),
        cwd=tmp_path,
    )

    assert result.stderr.splitlines() == ["hello stderr"]


@pytest.mark.asyncio
async def test_captures_stdout_and_stderr(runner: CommandRunner, tmp_path: Path) -> None:
    result = await runner.run(
        python_command(
            "import sys; print('out'); print('err', file=sys.stderr)",
        ),
        cwd=tmp_path,
    )

    assert result.stdout.splitlines() == ["out"]
    assert result.stderr.splitlines() == ["err"]


@pytest.mark.asyncio
async def test_non_zero_exit_code_is_returned(runner: CommandRunner, tmp_path: Path) -> None:
    result = await runner.run(python_command("raise SystemExit(7)"), cwd=tmp_path)

    assert result.exit_code == 7
    assert result.timed_out is False


@pytest.mark.asyncio
async def test_timeout_returns_timed_out(runner: CommandRunner, tmp_path: Path) -> None:
    result = await runner.run(
        python_command("import time; time.sleep(10)"),
        cwd=tmp_path,
        timeout_seconds=0.2,
    )

    assert result.timed_out is True
    assert result.exit_code is None


@pytest.mark.asyncio
async def test_timeout_process_is_terminated(runner: CommandRunner, tmp_path: Path) -> None:
    marker = tmp_path / "marker.txt"
    code = (
        "import pathlib, time; "
        f"path = pathlib.Path({str(marker)!r}); "
        "time.sleep(2); "
        "path.write_text('still-running', encoding='utf-8')"
    )

    result = await runner.run(python_command(code), cwd=tmp_path, timeout_seconds=0.2)

    assert result.timed_out is True
    assert not marker.exists()


@pytest.mark.asyncio
async def test_missing_executable_raises_clear_error(
    runner: CommandRunner,
    tmp_path: Path,
) -> None:
    with pytest.raises(CommandRunnerError, match="Executable not found"):
        await runner.run(["definitely-not-a-devconductor-command"], cwd=tmp_path)


@pytest.mark.asyncio
async def test_missing_cwd_raises_clear_error(runner: CommandRunner, tmp_path: Path) -> None:
    with pytest.raises(CommandRunnerError, match="Working directory does not exist"):
        await runner.run(python_command("pass"), cwd=tmp_path / "missing")


@pytest.mark.asyncio
async def test_file_cwd_raises_clear_error(runner: CommandRunner, tmp_path: Path) -> None:
    file_path = tmp_path / "not-a-directory.txt"
    file_path.write_text("content", encoding="utf-8")

    with pytest.raises(CommandRunnerError, match="Working directory is not a directory"):
        await runner.run(python_command("pass"), cwd=file_path)


@pytest.mark.asyncio
async def test_working_directory_with_spaces_runs(runner: CommandRunner, tmp_path: Path) -> None:
    cwd = tmp_path / "path with spaces"
    cwd.mkdir()

    result = await runner.run(
        python_command("import pathlib; print(pathlib.Path.cwd().name)"),
        cwd=cwd,
    )

    assert result.stdout.splitlines() == ["path with spaces"]


@pytest.mark.asyncio
async def test_chinese_working_directory_runs(runner: CommandRunner, tmp_path: Path) -> None:
    cwd = tmp_path / "课程资料"
    cwd.mkdir()

    result = await runner.run(
        python_command("import pathlib; print(pathlib.Path.cwd().name)"),
        cwd=cwd,
    )

    assert result.stdout.splitlines() == ["课程资料"]


@pytest.mark.asyncio
async def test_child_reads_env_override(runner: CommandRunner, tmp_path: Path) -> None:
    result = await runner.run(
        python_command("import os; print(os.environ['DEVCONDUCTOR_TEST_VALUE'])"),
        cwd=tmp_path,
        env={"DEVCONDUCTOR_TEST_VALUE": "overridden"},
    )

    assert result.stdout.splitlines() == ["overridden"]


@pytest.mark.asyncio
async def test_env_override_preserves_inherited_environment(
    runner: CommandRunner,
    tmp_path: Path,
) -> None:
    result = await runner.run(
        python_command("import os; print('PATH' in os.environ)"),
        cwd=tmp_path,
        env={"DEVCONDUCTOR_TEST_VALUE": "value"},
    )

    assert result.stdout.splitlines() == ["True"]


@pytest.mark.asyncio
async def test_env_override_does_not_modify_parent_environment(
    runner: CommandRunner,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEVCONDUCTOR_PARENT_UNCHANGED", raising=False)

    await runner.run(
        python_command("pass"),
        cwd=tmp_path,
        env={"DEVCONDUCTOR_PARENT_UNCHANGED": "child-only"},
    )

    assert "DEVCONDUCTOR_PARENT_UNCHANGED" not in os.environ


@pytest.mark.asyncio
async def test_command_list_is_not_modified(runner: CommandRunner, tmp_path: Path) -> None:
    command = python_command("print('ok')")
    original = list(command)

    await runner.run(command, cwd=tmp_path)

    assert command == original


@pytest.mark.asyncio
async def test_env_mapping_is_not_modified(runner: CommandRunner, tmp_path: Path) -> None:
    env: Mapping[str, str] = {"DEVCONDUCTOR_TEST_VALUE": "value"}

    await runner.run(python_command("pass"), cwd=tmp_path, env=env)

    assert env == {"DEVCONDUCTOR_TEST_VALUE": "value"}


@pytest.mark.asyncio
async def test_non_ascii_output_decodes_as_utf8(runner: CommandRunner, tmp_path: Path) -> None:
    result = await runner.run(python_command("print('中文 café')"), cwd=tmp_path)

    assert result.stdout.splitlines() == ["中文 café"]


@pytest.mark.asyncio
async def test_invalid_utf8_output_does_not_crash(runner: CommandRunner, tmp_path: Path) -> None:
    result = await runner.run(
        python_command("import sys; sys.stdout.buffer.write(b'valid\\xffinvalid')"),
        cwd=tmp_path,
    )

    assert result.stdout == "valid\ufffdinvalid"


@pytest.mark.asyncio
async def test_started_at_is_not_after_finished_at(runner: CommandRunner, tmp_path: Path) -> None:
    result = await runner.run(python_command("pass"), cwd=tmp_path)

    assert result.started_at <= result.finished_at


@pytest.mark.asyncio
async def test_result_validates_as_command_result(runner: CommandRunner, tmp_path: Path) -> None:
    result = await runner.run(python_command("print('ok')"), cwd=tmp_path)

    validated = CommandResult.model_validate(result.model_dump())

    assert validated == result


@pytest.mark.asyncio
async def test_runner_rejects_invalid_command_model_input(
    runner: CommandRunner,
    tmp_path: Path,
) -> None:
    with pytest.raises(CommandRunnerError, match="Command must contain at least one argument"):
        await runner.run([], cwd=tmp_path)


@pytest.mark.asyncio
async def test_no_timeout_child_process_remains(runner: CommandRunner, tmp_path: Path) -> None:
    marker = tmp_path / "leftover-marker.txt"
    code = (
        "import pathlib, time; "
        f"path = pathlib.Path({str(marker)!r}); "
        "time.sleep(0.8); "
        "path.write_text('leftover', encoding='utf-8')"
    )

    result = await runner.run(
        python_command(code),
        cwd=tmp_path,
        timeout_seconds=0.1,
    )
    await asyncio.sleep(1)

    assert result.timed_out is True
    assert not marker.exists()


@pytest.mark.asyncio
async def test_multiple_runs_do_not_share_state(runner: CommandRunner, tmp_path: Path) -> None:
    first = await runner.run(
        python_command("import os; print(os.environ['DEVCONDUCTOR_RUN_VALUE'])"),
        cwd=tmp_path,
        env={"DEVCONDUCTOR_RUN_VALUE": "first"},
    )
    second = await runner.run(
        python_command("import os; print(os.environ.get('DEVCONDUCTOR_RUN_VALUE', 'missing'))"),
        cwd=tmp_path,
    )

    assert first.stdout.splitlines() == ["first"]
    assert second.stdout.splitlines() == ["missing"]
