"""Workspace management contracts."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator, model_validator

from backend.app.schemas.base import ContractModel
from backend.app.schemas.task import _validate_non_empty_string


def _validate_relative_workspace_path(path: Path) -> Path:
    if path.is_absolute():
        raise ValueError("workspace paths must be relative")
    if any(part in {"..", ""} for part in path.parts):
        raise ValueError("workspace paths must not escape the workspace")
    return path


class WorkspaceHandle(ContractModel):
    """A managed Git worktree created for one isolated run."""

    workspace_id: str
    repo_path: Path
    worktree_path: Path
    branch_name: str
    base_ref: str
    base_commit: str
    created_at: datetime

    @field_validator("workspace_id", "branch_name", "base_ref", "base_commit")
    @classmethod
    def required_text(cls, value: str, info: Any) -> str:
        return _validate_non_empty_string(value, info.field_name)

    @field_validator("created_at")
    @classmethod
    def created_at_must_be_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value.astimezone(UTC)


class WorkspaceChanges(ContractModel):
    """Collected file changes and unified diff for a managed worktree."""

    changed_files: list[Path] = Field(default_factory=list)
    diff: str = ""
    has_changes: bool = False

    @model_validator(mode="before")
    @classmethod
    def normalize_and_validate(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        values = dict(data)
        changed_files = cls._dedupe_paths(values.get("changed_files", []))
        values["changed_files"] = changed_files

        expected_has_changes = bool(changed_files or values.get("diff", ""))
        supplied_has_changes = values.get("has_changes")
        if supplied_has_changes is None:
            values["has_changes"] = expected_has_changes
        elif supplied_has_changes != expected_has_changes:
            raise ValueError("has_changes is inconsistent with changed_files and diff")

        return values

    @staticmethod
    def _dedupe_paths(paths: Any) -> list[str]:
        seen: set[Path] = set()
        deduped: list[str] = []
        for raw_path in paths:
            path = _validate_relative_workspace_path(Path(raw_path))
            if path not in seen:
                seen.add(path)
                deduped.append(str(path))
        return deduped
