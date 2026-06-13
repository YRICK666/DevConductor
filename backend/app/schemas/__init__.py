"""Vendor-neutral structured contracts for DevConductor."""

from backend.app.schemas.command import CommandResult, VerificationResult
from backend.app.schemas.run import RunReport, RunStatus
from backend.app.schemas.task import TaskBudget, TaskConstraints, TaskSpec
from backend.app.schemas.verification import VerificationSpec, VerificationSummary

__all__ = [
    "CommandResult",
    "RunReport",
    "RunStatus",
    "TaskBudget",
    "TaskConstraints",
    "TaskSpec",
    "VerificationResult",
    "VerificationSpec",
    "VerificationSummary",
]
