"""Git worktree lifecycle management."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from backend.app.execution import CommandRunner
from backend.app.execution.exceptions import CommandRunnerError
from backend.app.schemas.command import CommandResult
from backend.app.schemas.workspace import WorkspaceChanges, WorkspaceHandle
from backend.app.workspace.exceptions import WorkspaceError

_SAFE_WORKSPACE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class _CommandRunner(Protocol):
    async def run(
        self,
        command: list[str],
        *,
        cwd: Path,
        timeout_seconds: float | None = None,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult: ...


class WorkspaceManager:
    """Create, inspect, and remove managed Git worktrees."""

    def __init__(self, command_runner: _CommandRunner | None = None) -> None:
        self._command_runner = command_runner or CommandRunner()

    async def create(
        self,
        *,
        repo_path: Path,
        workspace_id: str,
        base_ref: str = "HEAD",
    ) -> WorkspaceHandle:
        """Create a managed worktree on an isolated branch."""

        safe_workspace_id = self._validate_workspace_id(workspace_id)
        safe_base_ref = self._validate_non_empty(base_ref, "base_ref")
        repo_root = await self._validate_repo(repo_path)
        base_commit = (
            await self._run_git(
                ["git", "rev-parse", "--verify", f"{safe_base_ref}^{{commit}}"],
                cwd=repo_root,
                action="resolve base ref",
            )
        ).stdout.strip()

        branch_name = f"devconductor/{safe_workspace_id}"
        await self._ensure_branch_absent(repo_root, branch_name)

        worktree_path = self._managed_worktree_path(repo_root, safe_workspace_id)
        if worktree_path.exists():
            raise WorkspaceError(f"Worktree path already exists: {worktree_path}")

        worktree_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            await self._run_git(
                [
                    "git",
                    "worktree",
                    "add",
                    "-b",
                    branch_name,
                    str(worktree_path),
                    base_commit,
                ],
                cwd=repo_root,
                action="create worktree",
            )
            if not worktree_path.exists():
                raise WorkspaceError(f"Git did not create worktree path: {worktree_path}")
        except WorkspaceError as exc:
            cleanup_errors = await self._cleanup_after_create_failure(
                repo_root=repo_root,
                worktree_path=worktree_path,
                branch_name=branch_name,
            )
            if cleanup_errors:
                details = "; ".join(cleanup_errors)
                raise WorkspaceError(f"{exc}; cleanup also failed: {details}") from exc
            raise

        return WorkspaceHandle(
            workspace_id=safe_workspace_id,
            repo_path=repo_root,
            worktree_path=worktree_path,
            branch_name=branch_name,
            base_ref=safe_base_ref,
            base_commit=base_commit,
            created_at=datetime.now(UTC),
        )

    async def collect_changes(self, workspace: WorkspaceHandle) -> WorkspaceChanges:
        """Collect changed file paths and a reviewable diff without touching the real index."""

        self._validate_managed_workspace(workspace)
        status = await self._run_git(
            ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
            cwd=workspace.worktree_path,
            action="collect worktree status",
        )
        changed_files = self._parse_porcelain_paths(status.stdout)

        index_path = self._temporary_index_path(workspace)
        env = {"GIT_INDEX_FILE": str(index_path)}
        try:
            await self._run_git(
                ["git", "read-tree", workspace.base_commit],
                cwd=workspace.worktree_path,
                env=env,
                action="prepare temporary index",
            )
            await self._run_git(
                ["git", "add", "-A", "--", "."],
                cwd=workspace.worktree_path,
                env=env,
                action="snapshot worktree changes",
            )
            diff = (
                await self._run_git(
                    ["git", "diff", "--cached", "--binary", workspace.base_commit],
                    cwd=workspace.worktree_path,
                    env=env,
                    action="collect worktree diff",
                )
            ).stdout
        finally:
            self._delete_temporary_index(index_path)

        return WorkspaceChanges(changed_files=changed_files, diff=diff)

    async def remove(
        self,
        workspace: WorkspaceHandle,
        *,
        force: bool = False,
        delete_branch: bool = False,
    ) -> None:
        """Remove a managed worktree and optionally delete its matching branch."""

        self._validate_managed_workspace(workspace)
        command = ["git", "worktree", "remove"]
        if force:
            command.append("--force")
        command.append(str(workspace.worktree_path))
        await self._run_git(command, cwd=workspace.repo_path, action="remove worktree")

        list_output = (
            await self._run_git(
                ["git", "worktree", "list", "--porcelain"],
                cwd=workspace.repo_path,
                action="confirm worktree removal",
            )
        ).stdout
        if self._path_in_worktree_list(workspace.worktree_path, list_output):
            raise WorkspaceError(f"Worktree still exists after removal: {workspace.worktree_path}")

        if delete_branch:
            expected_branch = f"devconductor/{workspace.workspace_id}"
            if workspace.branch_name != expected_branch:
                raise WorkspaceError("Refusing to delete a branch not owned by this workspace")
            await self._run_git(
                ["git", "branch", "-d", workspace.branch_name],
                cwd=workspace.repo_path,
                action="delete workspace branch",
            )

    async def _validate_repo(self, repo_path: Path) -> Path:
        if not repo_path.exists():
            raise WorkspaceError(f"Repository path does not exist: {repo_path}")
        if not repo_path.is_dir():
            raise WorkspaceError(f"Repository path is not a directory: {repo_path}")

        result = await self._run_git(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=repo_path,
            action="validate git repository",
        )
        return Path(result.stdout.strip()).resolve()

    async def _ensure_branch_absent(self, repo_root: Path, branch_name: str) -> None:
        result = await self._run_git(
            ["git", "branch", "--list", branch_name],
            cwd=repo_root,
            action="check workspace branch",
        )
        if result.stdout.strip():
            raise WorkspaceError(f"Workspace branch already exists: {branch_name}")

    async def _cleanup_after_create_failure(
        self,
        *,
        repo_root: Path,
        worktree_path: Path,
        branch_name: str,
    ) -> list[str]:
        errors: list[str] = []
        if worktree_path.exists():
            try:
                await self._run_git(
                    ["git", "worktree", "remove", "--force", str(worktree_path)],
                    cwd=repo_root,
                    action="clean up failed worktree",
                )
            except WorkspaceError as exc:
                errors.append(str(exc))

        try:
            branch_list = await self._run_git(
                ["git", "branch", "--list", branch_name],
                cwd=repo_root,
                action="check failed workspace branch",
            )
            if branch_list.stdout.strip():
                await self._run_git(
                    ["git", "branch", "-d", branch_name],
                    cwd=repo_root,
                    action="delete failed workspace branch",
                )
        except WorkspaceError as exc:
            errors.append(str(exc))
        return errors

    async def _run_git(
        self,
        command: list[str],
        *,
        cwd: Path,
        action: str,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        try:
            result = await self._command_runner.run(command, cwd=cwd, env=env)
        except CommandRunnerError as exc:
            raise WorkspaceError(f"Unable to {action}: {exc}") from exc

        if result.timed_out:
            raise WorkspaceError(f"Unable to {action}: git command timed out")
        if result.exit_code != 0:
            message = result.stderr.strip() or result.stdout.strip() or "git command failed"
            raise WorkspaceError(f"Unable to {action}: {message}")
        return result

    def _managed_worktree_path(self, repo_root: Path, workspace_id: str) -> Path:
        root = (repo_root / ".worktrees").resolve()
        path = (root / workspace_id).resolve()
        if path.parent != root:
            raise WorkspaceError("Workspace path escapes the managed worktree root")
        return path

    def _validate_managed_workspace(self, workspace: WorkspaceHandle) -> None:
        expected_branch = f"devconductor/{workspace.workspace_id}"
        if workspace.branch_name != expected_branch:
            raise WorkspaceError("Workspace branch does not match workspace_id")
        expected_path = self._managed_worktree_path(workspace.repo_path, workspace.workspace_id)
        if workspace.worktree_path.resolve() != expected_path:
            raise WorkspaceError("Workspace path is not managed by this repository")
        if workspace.worktree_path.resolve() == workspace.repo_path.resolve():
            raise WorkspaceError("Refusing to operate on the main repository worktree")

    def _temporary_index_path(self, workspace: WorkspaceHandle) -> Path:
        indexes_dir = workspace.repo_path / ".worktrees" / ".indexes"
        indexes_dir.mkdir(parents=True, exist_ok=True)
        return indexes_dir / f"{workspace.workspace_id}-{uuid4().hex}.index"

    @staticmethod
    def _delete_temporary_index(index_path: Path) -> None:
        for candidate in (index_path, Path(f"{index_path}.lock")):
            try:
                candidate.unlink()
            except FileNotFoundError:
                pass

    @staticmethod
    def _parse_porcelain_paths(output: str) -> list[Path]:
        entries = [entry for entry in output.split("\0") if entry]
        paths: list[Path] = []
        index = 0
        while index < len(entries):
            entry = entries[index]
            if len(entry) < 4:
                index += 1
                continue

            status = entry[:2]
            path_text = entry[3:]
            paths.append(Path(path_text))
            index += 1
            if "R" in status or "C" in status:
                index += 1
        return sorted(dict.fromkeys(paths))

    @staticmethod
    def _path_in_worktree_list(worktree_path: Path, output: str) -> bool:
        expected = worktree_path.resolve()
        for line in output.splitlines():
            if not line.startswith("worktree "):
                continue
            if Path(line.removeprefix("worktree ")).resolve() == expected:
                return True
        return False

    @staticmethod
    def _validate_workspace_id(workspace_id: str) -> str:
        value = WorkspaceManager._validate_non_empty(workspace_id, "workspace_id")
        path_value = Path(value)
        if (
            path_value.is_absolute()
            or ".." in value
            or "/" in value
            or "\\" in value
            or not _SAFE_WORKSPACE_ID.fullmatch(value)
        ):
            raise WorkspaceError("workspace_id contains unsafe path characters")
        return value

    @staticmethod
    def _validate_non_empty(value: str, field_name: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise WorkspaceError(f"{field_name} must not be empty")
        return stripped
