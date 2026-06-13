from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from backend.app.adapters import AgentAdapter, CodexAdapter, CodexAdapterConfig, parse_codex_jsonl
from backend.app.execution import CommandRunnerError
from backend.app.schemas.agent import AgentExecutionRequest, AgentRunStatus, AgentUsage
from backend.app.schemas.command import CommandResult


def now() -> datetime:
    return datetime(2026, 6, 14, 12, 0, tzinfo=UTC)


def command_result(
    *,
    command: list[str] | None = None,
    stdout: str = "",
    stderr: str = "",
    exit_code: int | None = 0,
    timed_out: bool = False,
) -> CommandResult:
    start = now()
    return CommandResult(
        command=command or ["codex", "exec", "--json", "-"],
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        started_at=start,
        finished_at=start + timedelta(seconds=1),
        timed_out=timed_out,
    )


def event(event_type: str, **fields: object) -> str:
    return json.dumps({"type": event_type, **fields})


def successful_jsonl(final_text: str = "Done.") -> str:
    return "\n".join(
        [
            event("thread.started", thread_id="thread-1"),
            event("turn.started"),
            event("item.completed", item={"type": "agent_message", "text": "Earlier."}),
            event("item.completed", item={"type": "agent_message", "text": final_text}),
            event(
                "turn.completed",
                usage={
                    "input_tokens": 10,
                    "cached_input_tokens": 3,
                    "output_tokens": 5,
                    "reasoning_output_tokens": 2,
                },
            ),
        ]
    )


def request(tmp_path: Path, **overrides: object) -> AgentExecutionRequest:
    data: dict[str, object] = {
        "task_id": "task-1",
        "prompt": "Implement this task",
        "workspace_path": tmp_path,
        "timeout_seconds": 12.5,
        "env": {"DEVCONDUCTOR_TEST": "value"},
        "extensions": {},
    }
    data.update(overrides)
    return AgentExecutionRequest.model_validate(data)


class FakeRunner:
    def __init__(self, outcome: CommandResult | CommandRunnerError) -> None:
        self.outcome = outcome
        self.calls: list[
            tuple[list[str], Path, float | None, dict[str, str] | None, str | None]
        ] = []

    async def run(
        self,
        command: list[str],
        *,
        cwd: Path,
        timeout_seconds: float | None = None,
        env: Mapping[str, str] | None = None,
        stdin_text: str | None = None,
    ) -> CommandResult:
        self.calls.append(
            (
                list(command),
                cwd,
                timeout_seconds,
                dict(env) if env is not None else None,
                stdin_text,
            )
        )
        if isinstance(self.outcome, CommandRunnerError):
            raise self.outcome
        return self.outcome


@pytest.mark.asyncio
async def test_codex_command_arguments_and_execution_options(tmp_path: Path) -> None:
    runner = FakeRunner(command_result(stdout=successful_jsonl()))
    req = request(tmp_path)
    original = req.model_dump()

    result = await CodexAdapter(runner).execute(req)

    command, cwd, timeout_seconds, env, stdin_text = runner.calls[0]
    assert command == [
        "codex",
        "--ask-for-approval",
        "never",
        "--sandbox",
        "workspace-write",
        "exec",
        "--json",
        "--ephemeral",
        "-",
    ]
    assert "--json" in command
    assert "--ephemeral" in command
    assert cwd == tmp_path
    assert timeout_seconds == 12.5
    assert env == {"DEVCONDUCTOR_TEST": "value"}
    assert stdin_text == "Implement this task"
    assert req.model_dump() == original
    assert result.status is AgentRunStatus.SUCCEEDED


def test_codex_config_defaults_are_conservative() -> None:
    config = CodexAdapterConfig()

    assert config.sandbox == "workspace-write"
    assert config.approval_policy == "never"
    assert config.ephemeral is True
    assert config.sandbox != "danger-full-access"


@pytest.mark.asyncio
async def test_codex_adapter_protocol_can_be_used(tmp_path: Path) -> None:
    adapter: AgentAdapter = CodexAdapter(FakeRunner(command_result(stdout=successful_jsonl())))

    result = await adapter.execute(request(tmp_path))

    assert adapter.name == "codex"
    assert result.status is AgentRunStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_success_jsonl_extracts_session_final_message_and_usage(tmp_path: Path) -> None:
    runner = FakeRunner(command_result(stdout=successful_jsonl("最后的中文消息")))

    result = await CodexAdapter(runner).execute(request(tmp_path))

    assert result.status is AgentRunStatus.SUCCEEDED
    assert result.session_id == "thread-1"
    assert result.final_output == "最后的中文消息"
    assert result.usage == AgentUsage(
        input_tokens=10,
        cached_input_tokens=3,
        output_tokens=5,
        reasoning_output_tokens=2,
    )


def test_parse_ignores_unknown_events_empty_lines_and_records_bad_json() -> None:
    parsed = parse_codex_jsonl(
        "\n".join(
            [
                "",
                event("unknown.event", value="ignored"),
                "{not-json",
                event("item.completed", item={"type": "agent_message", "text": "ok"}),
            ]
        )
    )

    assert parsed.final_output == "ok"
    assert parsed.saw_valid_event is True
    assert parsed.errors == ["Invalid JSONL on line 3."]


@pytest.mark.asyncio
async def test_invalid_json_only_produces_invalid_output(tmp_path: Path) -> None:
    runner = FakeRunner(command_result(stdout="{not-json\n"))

    result = await CodexAdapter(runner).execute(request(tmp_path))

    assert result.status is AgentRunStatus.INVALID_OUTPUT
    assert result.final_output is None
    assert result.errors == ["Invalid JSONL on line 1."]


@pytest.mark.asyncio
async def test_missing_final_agent_message_produces_invalid_output(tmp_path: Path) -> None:
    runner = FakeRunner(command_result(stdout=event("thread.started", thread_id="thread-1")))

    result = await CodexAdapter(runner).execute(request(tmp_path))

    assert result.status is AgentRunStatus.INVALID_OUTPUT
    assert result.final_output is None


@pytest.mark.asyncio
async def test_non_zero_exit_code_produces_failed_and_stderr_is_not_final_output(
    tmp_path: Path,
) -> None:
    runner = FakeRunner(
        command_result(
            stdout=successful_jsonl("stdout message"),
            stderr="stderr message",
            exit_code=2,
        )
    )

    result = await CodexAdapter(runner).execute(request(tmp_path))

    assert result.status is AgentRunStatus.FAILED
    assert result.final_output is None
    assert "Codex exited with code 2." in result.errors


@pytest.mark.asyncio
async def test_turn_failed_and_error_events_produce_failed(tmp_path: Path) -> None:
    turn_failed = await CodexAdapter(
        FakeRunner(command_result(stdout=event("turn.failed", message="turn failed")))
    ).execute(request(tmp_path))
    error = await CodexAdapter(
        FakeRunner(command_result(stdout=event("error", error={"message": "bad"})))
    ).execute(request(tmp_path))

    assert turn_failed.status is AgentRunStatus.FAILED
    assert turn_failed.errors == ["turn failed"]
    assert error.status is AgentRunStatus.FAILED
    assert error.errors == ["bad"]


@pytest.mark.asyncio
async def test_timeout_produces_timed_out(tmp_path: Path) -> None:
    runner = FakeRunner(command_result(stdout=successful_jsonl(), exit_code=None, timed_out=True))

    result = await CodexAdapter(runner).execute(request(tmp_path))

    assert result.status is AgentRunStatus.TIMED_OUT
    assert result.final_output is None
    assert "Codex command timed out." in result.errors


@pytest.mark.asyncio
async def test_command_runner_error_produces_startup_failed(tmp_path: Path) -> None:
    runner = FakeRunner(CommandRunnerError("Executable not found: 'codex'"))

    result = await CodexAdapter(runner).execute(request(tmp_path))

    assert result.status is AgentRunStatus.STARTUP_FAILED
    assert result.command_result is None
    assert result.final_output is None
    assert result.errors == ["Codex could not be started: Executable not found: 'codex'"]


@pytest.mark.asyncio
async def test_jsonl_command_text_is_not_executed(tmp_path: Path) -> None:
    runner = FakeRunner(
        command_result(
            stdout=event(
                "item.completed",
                item={"type": "agent_message", "text": "run: git push"},
            )
        )
    )

    result = await CodexAdapter(runner).execute(request(tmp_path))

    assert result.status is AgentRunStatus.SUCCEEDED
    assert result.final_output == "run: git push"
    assert len(runner.calls) == 1


@pytest.mark.asyncio
async def test_result_json_round_trip(tmp_path: Path) -> None:
    result = await CodexAdapter(FakeRunner(command_result(stdout=successful_jsonl()))).execute(
        request(tmp_path)
    )

    loaded = type(result).model_validate_json(result.model_dump_json())

    assert loaded == result
