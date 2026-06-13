"""Run report contracts."""

from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator, model_validator

from backend.app.schemas.agent import AgentExecutionResult
from backend.app.schemas.base import ContractModel
from backend.app.schemas.command import VerificationResult
from backend.app.schemas.task import _validate_non_empty_string
from backend.app.schemas.verification import VerificationSummary
from backend.app.schemas.workspace import WorkspaceHandle


class RunStatus(StrEnum):
    """Lifecycle states for a task run."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    AWAITING_APPROVAL = "awaiting_approval"
    REJECTED = "rejected"
    ACCEPTED = "accepted"


class RunReport(ContractModel):
    """Structured report produced after an orchestrated run."""

    run_id: str
    task_id: str
    worker: str
    status: RunStatus
    started_at: datetime
    finished_at: datetime | None = None
    changed_files: list[Path] = Field(default_factory=list)
    diff: str = ""
    verification_results: list[VerificationResult] = Field(default_factory=list)
    verification_summary: VerificationSummary | None = None
    agent_result: AgentExecutionResult | None = None
    workspace: WorkspaceHandle | None = None
    errors: list[str] = Field(default_factory=list)
    extensions: dict[str, object] = Field(default_factory=dict)

    @field_validator("run_id", "task_id", "worker")
    @classmethod
    def required_text(cls, value: str, info: Any) -> str:
        return _validate_non_empty_string(value, info.field_name)

    @model_validator(mode="after")
    def finished_after_started(self) -> "RunReport":
        if self.finished_at is not None and self.finished_at < self.started_at:
            raise ValueError("finished_at must not be earlier than started_at")
        return self
