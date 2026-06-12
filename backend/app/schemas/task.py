"""Task input contracts."""

from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator

from backend.app.schemas.base import ContractModel


def _validate_non_empty_string(value: str, field_name: str) -> str:
    if not value:
        raise ValueError(f"{field_name} must not be empty")
    return value


def _validate_command_arguments(command: Any) -> list[str]:
    if isinstance(command, str) or not isinstance(command, list):
        raise ValueError("command must be an argument array")
    if not command:
        raise ValueError("command must contain at least one argument")

    validated: list[str] = []
    for argument in command:
        if not isinstance(argument, str):
            raise ValueError("command arguments must be strings")
        stripped = argument.strip()
        if not stripped:
            raise ValueError("command arguments must not be empty")
        validated.append(stripped)
    return validated


class TaskConstraints(ContractModel):
    """Policy constraints supplied with a task."""

    allowed_files: list[Path] = Field(default_factory=list)
    forbidden_operations: list[str] = Field(default_factory=list)
    allow_network: bool = False
    allow_repo_external_paths: bool = False


class TaskBudget(ContractModel):
    """Resource limits for a task run."""

    max_turns: int = Field(gt=0)
    timeout_seconds: int = Field(gt=0)
    max_cost_usd: Decimal = Field(ge=Decimal("0"))


class TaskSpec(ContractModel):
    """Vendor-neutral task specification consumed by the orchestrator."""

    id: str
    repo_path: Path
    objective: str
    worker: str
    constraints: TaskConstraints = Field(default_factory=TaskConstraints)
    acceptance_criteria: list[str]
    test_commands: list[list[str]] = Field(default_factory=list)
    budget: TaskBudget
    extensions: dict[str, object] = Field(default_factory=dict)

    @field_validator("id", "objective", "worker")
    @classmethod
    def required_text(cls, value: str, info: Any) -> str:
        return _validate_non_empty_string(value, info.field_name)

    @field_validator("acceptance_criteria")
    @classmethod
    def acceptance_criteria_must_be_non_empty(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("acceptance_criteria must contain at least one item")
        for criterion in value:
            if not criterion.strip():
                raise ValueError("acceptance_criteria items must not be empty")
        return value

    @field_validator("test_commands", mode="before")
    @classmethod
    def test_commands_must_be_argument_arrays(cls, value: Any) -> Any:
        if value is None:
            return []
        if isinstance(value, str) or not isinstance(value, list):
            raise ValueError("test_commands must be a list of argument arrays")
        return [_validate_command_arguments(command) for command in value]
