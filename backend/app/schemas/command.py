"""Command execution and verification result contracts."""

from datetime import datetime
from typing import Any

from pydantic import ConfigDict, field_validator, model_validator

from backend.app.schemas.base import ContractModel
from backend.app.schemas.task import _validate_command_arguments, _validate_non_empty_string


class CommandResult(ContractModel):
    """Facts captured from a real process execution."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=False,
        validate_assignment=True,
    )

    command: list[str]
    exit_code: int | None
    stdout: str = ""
    stderr: str = ""
    started_at: datetime
    finished_at: datetime
    timed_out: bool

    @field_validator("command", mode="before")
    @classmethod
    def command_must_have_arguments(cls, value: Any) -> list[str]:
        return _validate_command_arguments(value)

    @model_validator(mode="after")
    def finished_after_started(self) -> "CommandResult":
        if self.finished_at < self.started_at:
            raise ValueError("finished_at must not be earlier than started_at")
        return self


class VerificationResult(ContractModel):
    """Deterministic verification produced by an executed command."""

    name: str
    command_result: CommandResult | None
    passed: bool
    required: bool = True
    details: str | None = None

    @field_validator("name")
    @classmethod
    def name_must_not_be_empty(cls, value: str) -> str:
        return _validate_non_empty_string(value, "name")
