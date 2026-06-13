"""Vendor-neutral agent execution contracts."""

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator, model_validator

from backend.app.schemas.base import ContractModel
from backend.app.schemas.command import CommandResult
from backend.app.schemas.task import _validate_non_empty_string


class AgentRunStatus(StrEnum):
    """Mutually exclusive states for one agent process invocation."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    STARTUP_FAILED = "startup_failed"
    INVALID_OUTPUT = "invalid_output"


class AgentExecutionRequest(ContractModel):
    """Vendor-neutral request passed to an agent adapter."""

    task_id: str
    prompt: str
    workspace_path: Path
    timeout_seconds: float | None = None
    env: dict[str, str] = Field(default_factory=dict)
    extensions: dict[str, object] = Field(default_factory=dict)

    @field_validator("task_id", "prompt")
    @classmethod
    def required_text(cls, value: str, info: Any) -> str:
        return _validate_non_empty_string(value, info.field_name)

    @field_validator("timeout_seconds")
    @classmethod
    def timeout_must_be_positive(cls, value: float | None) -> float | None:
        if value is not None and value <= 0:
            raise ValueError("timeout_seconds must be greater than 0")
        return value


class AgentUsage(ContractModel):
    """Vendor-neutral token usage fields that may be reported by an agent."""

    input_tokens: int | None = Field(default=None, ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    reasoning_output_tokens: int | None = Field(default=None, ge=0)


class AgentExecutionResult(ContractModel):
    """Structured outcome from one agent adapter execution."""

    agent_name: str
    task_id: str
    status: AgentRunStatus
    started_at: datetime
    finished_at: datetime
    final_output: str | None = None
    session_id: str | None = None
    usage: AgentUsage | None = None
    command_result: CommandResult | None = None
    errors: list[str] = Field(default_factory=list)
    extensions: dict[str, object] = Field(default_factory=dict)

    @field_validator("agent_name", "task_id")
    @classmethod
    def required_text(cls, value: str, info: Any) -> str:
        return _validate_non_empty_string(value, info.field_name)

    @field_validator("started_at", "finished_at")
    @classmethod
    def timestamps_must_be_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def finished_after_started(self) -> "AgentExecutionResult":
        if self.finished_at < self.started_at:
            raise ValueError("finished_at must not be earlier than started_at")
        return self
