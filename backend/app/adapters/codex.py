"""Codex CLI adapter."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from backend.app.execution import CommandRunner
from backend.app.execution.exceptions import CommandRunnerError
from backend.app.schemas.agent import (
    AgentExecutionRequest,
    AgentExecutionResult,
    AgentModelProfile,
    AgentRunStatus,
    AgentUsage,
)
from backend.app.schemas.command import CommandResult


class _CommandRunner(Protocol):
    async def run(
        self,
        command: list[str],
        *,
        cwd: Path,
        timeout_seconds: float | None = None,
        env: Mapping[str, str] | None = None,
        stdin_text: str | None = None,
    ) -> CommandResult: ...


@dataclass(frozen=True)
class CodexAdapterConfig:
    """Codex-specific CLI configuration."""

    executable: str = "codex"
    sandbox: str = "workspace-write"
    approval_policy: str = "never"
    profile: AgentModelProfile = AgentModelProfile.MINI
    ephemeral: bool = True
    extra_args: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CodexJsonlParseResult:
    """Parsed facts from Codex JSONL output."""

    final_output: str | None
    session_id: str | None
    reported_model: str | None
    model_metadata: dict[str, object]
    usage: AgentUsage | None
    errors: list[str]
    saw_valid_event: bool
    saw_agent_error: bool


class CodexAdapter:
    """Execute Codex CLI and convert JSONL output to a vendor-neutral result."""

    name = "codex"

    def __init__(
        self,
        command_runner: _CommandRunner | None = None,
        config: CodexAdapterConfig | None = None,
    ) -> None:
        self._command_runner = command_runner or CommandRunner()
        self._config = config or CodexAdapterConfig()

    async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult:
        """Run ``codex exec --json`` in the provided workspace."""

        command = self._build_command()
        started_at = datetime.now(UTC)
        try:
            command_result = await self._command_runner.run(
                command,
                cwd=request.workspace_path,
                timeout_seconds=request.timeout_seconds,
                env=dict(request.env),
                stdin_text=request.prompt,
            )
        except CommandRunnerError as exc:
            finished_at = datetime.now(UTC)
            return AgentExecutionResult(
                agent_name=self.name,
                task_id=request.task_id,
                status=AgentRunStatus.STARTUP_FAILED,
                started_at=started_at,
                finished_at=finished_at,
                profile=self._config.profile,
                elapsed_seconds=(finished_at - started_at).total_seconds(),
                attempt_count=1,
                command_result=None,
                errors=[f"Codex could not be started: {exc}"],
            )

        finished_at = datetime.now(UTC)
        elapsed_seconds = (finished_at - started_at).total_seconds()
        parsed = parse_codex_jsonl(command_result.stdout)
        status = self._status_for(command_result, parsed)
        errors = list(parsed.errors)
        if command_result.exit_code not in (0, None):
            errors.append(f"Codex exited with code {command_result.exit_code}.")
        if command_result.timed_out:
            errors.append("Codex command timed out.")

        return AgentExecutionResult(
            agent_name=self.name,
            task_id=request.task_id,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            final_output=parsed.final_output if status is AgentRunStatus.SUCCEEDED else None,
            session_id=parsed.session_id,
            profile=self._config.profile,
            reported_model=parsed.reported_model,
            model_metadata=parsed.model_metadata,
            usage=parsed.usage,
            elapsed_seconds=elapsed_seconds,
            attempt_count=1,
            command_result=command_result,
            errors=errors,
            extensions={
                "codex": {
                    "jsonl": True,
                    "ephemeral": self._config.ephemeral,
                    "profile": self._config.profile.value,
                }
            },
        )

    def _build_command(self) -> list[str]:
        command = [
            self._config.executable,
            "--ask-for-approval",
            self._config.approval_policy,
            "--sandbox",
            self._config.sandbox,
            "--profile",
            self._config.profile.value,
            "exec",
            "--json",
        ]
        if self._config.ephemeral:
            command.append("--ephemeral")
        command.extend(self._config.extra_args)
        command.append("-")
        return command

    @staticmethod
    def _status_for(
        command_result: CommandResult,
        parsed: CodexJsonlParseResult,
    ) -> AgentRunStatus:
        if command_result.timed_out:
            return AgentRunStatus.TIMED_OUT
        if command_result.exit_code != 0:
            return AgentRunStatus.FAILED
        if parsed.saw_agent_error:
            return AgentRunStatus.FAILED
        if not parsed.saw_valid_event or not parsed.final_output:
            return AgentRunStatus.INVALID_OUTPUT
        return AgentRunStatus.SUCCEEDED


def parse_codex_jsonl(output: str) -> CodexJsonlParseResult:
    """Parse Codex JSONL events without executing or trusting their contents."""

    final_output: str | None = None
    session_id: str | None = None
    reported_model: str | None = None
    model_metadata: dict[str, object] = {}
    usage: AgentUsage | None = None
    errors: list[str] = []
    saw_valid_event = False
    saw_agent_error = False

    for line_number, raw_line in enumerate(output.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            errors.append(f"Invalid JSONL on line {line_number}.")
            continue
        if not isinstance(event, dict):
            errors.append(f"Invalid JSONL event on line {line_number}.")
            continue

        saw_valid_event = True
        event_type = str(event.get("type", ""))
        if event_type == "thread.started":
            session_id = _extract_session_id(event) or session_id
            reported_model = _extract_reported_model(event) or reported_model
            model_metadata.update(_extract_model_metadata(event))
        elif event_type == "item.completed":
            message = _extract_agent_message(event)
            if message:
                final_output = message
        elif event_type == "turn.completed":
            usage = _extract_usage(event) or usage
            reported_model = _extract_reported_model(event) or reported_model
            model_metadata.update(_extract_model_metadata(event))
        elif event_type == "turn.failed":
            saw_agent_error = True
            errors.append(_extract_error_message(event, "Codex turn failed."))
            reported_model = _extract_reported_model(event) or reported_model
            model_metadata.update(_extract_model_metadata(event))
        elif event_type == "error":
            saw_agent_error = True
            errors.append(_extract_error_message(event, "Codex emitted an error."))
            reported_model = _extract_reported_model(event) or reported_model
            model_metadata.update(_extract_model_metadata(event))

    return CodexJsonlParseResult(
        final_output=final_output,
        session_id=session_id,
        reported_model=reported_model,
        model_metadata=model_metadata,
        usage=usage,
        errors=errors,
        saw_valid_event=saw_valid_event,
        saw_agent_error=saw_agent_error,
    )


def _extract_session_id(event: dict[str, Any]) -> str | None:
    for key in ("thread_id", "session_id", "id"):
        value = event.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    thread = event.get("thread")
    if isinstance(thread, dict):
        for key in ("id", "thread_id", "session_id"):
            value = thread.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _extract_agent_message(event: dict[str, Any]) -> str | None:
    item = event.get("item")
    if not isinstance(item, dict) or item.get("type") != "agent_message":
        return None

    for key in ("text", "message", "content"):
        value = item.get(key)
        text = _text_from_value(value)
        if text:
            return text
    return None


def _text_from_value(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, list):
        parts: list[str] = []
        for entry in value:
            if isinstance(entry, str):
                parts.append(entry)
            elif isinstance(entry, dict):
                text = entry.get("text")
                if isinstance(text, str):
                    parts.append(text)
        joined = "".join(parts).strip()
        return joined or None
    return None


def _extract_usage(event: dict[str, Any]) -> AgentUsage | None:
    raw_usage = event.get("usage")
    if not isinstance(raw_usage, dict):
        turn = event.get("turn")
        raw_usage = turn.get("usage") if isinstance(turn, dict) else None
    if not isinstance(raw_usage, dict):
        return None

    return AgentUsage(
        input_tokens=_optional_non_negative_int(raw_usage.get("input_tokens")),
        cached_input_tokens=_optional_non_negative_int(raw_usage.get("cached_input_tokens")),
        output_tokens=_optional_non_negative_int(raw_usage.get("output_tokens")),
        reasoning_output_tokens=_optional_non_negative_int(
            raw_usage.get("reasoning_output_tokens")
        ),
    )


def _extract_reported_model(event: dict[str, Any]) -> str | None:
    for source in _model_sources(event):
        for key in ("model", "model_id", "model_name"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _extract_model_metadata(event: dict[str, Any]) -> dict[str, object]:
    metadata: dict[str, object] = {}
    for source in _model_sources(event):
        for key in (
            "model",
            "model_id",
            "model_name",
            "provider",
            "profile",
            "effort",
            "reasoning_effort",
        ):
            value = source.get(key)
            if isinstance(value, (str, int, float, bool)):
                metadata[key] = value
    return metadata


def _model_sources(event: dict[str, Any]) -> list[dict[str, Any]]:
    sources = [event]
    for key in ("turn", "response", "metadata"):
        value = event.get(key)
        if isinstance(value, dict):
            sources.append(value)
    return sources


def _optional_non_negative_int(value: Any) -> int | None:
    if isinstance(value, int) and value >= 0:
        return value
    return None


def _extract_error_message(event: dict[str, Any], fallback: str) -> str:
    for key in ("message", "error"):
        value = event.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            message = value.get("message")
            if isinstance(message, str) and message.strip():
                return message.strip()
    return fallback
