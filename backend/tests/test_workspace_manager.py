from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.execution import CommandRunner
from backend.app.execution.exceptions import CommandRunnerError
from backend.app.schemas.command import CommandResult
from backend.app.schemas.workspace import WorkspaceChanges, WorkspaceHandle
from backend.app.workspace import WorkspaceError, WorkspaceManager


async def run_git(repo: Path, command: list[str]) -> CommandResult:
    result = await CommandRunner().run(["git", *command], cwd=repo)
    assert result.exit_code == 0, result.stderr
    return result


async def make_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    await run_git(path, ["init", "-b", "main"])
    await run_git(path, ["config", "user.name", "Dev Conductor Test"])
    await run_git(path, ["config", "user.email", "devconductor@example.test"])
    (path / "tracked.txt").write_text("base\n", encoding="utf-8")
    (path / "delete-me.txt").write_text("remove me\n", encoding="utf-8")
    await run_git(path, ["add", "tracked.txt", "delete-me.txt"])
    await run_git(path, ["commit", "-m", "initial"])
    return path


async def branch_exists(repo: Path, branch_name: str) -> bool:
    result = await run_git(repo, ["branch", "--list", branch_name])
    return bool(result.stdout.strip())


async def worktree_paths(repo: Path) -> list[Path]:
    result = await run_git(repo, ["worktree", "list", "--porcelain"])
    paths: list[Path] = []
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            paths.append(Path(line.removeprefix("worktree ")).resolve())
    return paths


async def create_workspace(repo: Path, workspace_id: str = "run-1") -> WorkspaceHandle:
    return await WorkspaceManager(CommandRunner()).create(
        repo_path=repo,
        workspace_id=workspace_id,
    )


@pytest.mark.asyncio
async def test_create_worktree_in_valid_git_repo_returns_handle(tmp_path: Path) -> None:
    repo = await make_repo(tmp_path / "repo")
    base = (await run_git(repo, ["rev-parse", "HEAD"])).stdout.strip()

    handle = await create_workspace(repo)

    assert handle.workspace_id == "run-1"
    assert handle.repo_path == repo.resolve()
    assert handle.worktree_path == (repo / ".worktrees" / "run-1").resolve()
    assert handle.branch_name == "devconductor/run-1"
    assert handle.base_ref == "HEAD"
    assert handle.base_commit == base
    assert handle.created_at.tzinfo is not None
    assert handle.created_at.utcoffset() == UTC.utcoffset(handle.created_at)
    assert handle.worktree_path.exists()


@pytest.mark.asyncio
async def test_worktree_is_based_on_resolved_commit_and_independent_branch(
    tmp_path: Path,
) -> None:
    repo = await make_repo(tmp_path / "repo")
    base = (await run_git(repo, ["rev-parse", "HEAD"])).stdout.strip()

    handle = await create_workspace(repo)
    worktree_head = (await run_git(handle.worktree_path, ["rev-parse", "HEAD"])).stdout.strip()
    worktree_branch = (
        await run_git(handle.worktree_path, ["branch", "--show-current"])
    ).stdout.strip()

    assert worktree_head == base
    assert worktree_branch == "devconductor/run-1"


@pytest.mark.asyncio
async def test_main_repo_uncommitted_changes_do_not_enter_worktree(tmp_path: Path) -> None:
    repo = await make_repo(tmp_path / "repo")
    (repo / "tracked.txt").write_text("dirty main\n", encoding="utf-8")
    (repo / "untracked.txt").write_text("main only\n", encoding="utf-8")

    handle = await create_workspace(repo)

    assert (handle.worktree_path / "tracked.txt").read_text(encoding="utf-8") == "base\n"
    assert not (handle.worktree_path / "untracked.txt").exists()


@pytest.mark.parametrize("workspace_id", ["", "   ", "../bad", "bad..id", "bad/name", "bad\\name"])
@pytest.mark.asyncio
async def test_create_rejects_unsafe_workspace_id(tmp_path: Path, workspace_id: str) -> None:
    repo = await make_repo(tmp_path / "repo")

    with pytest.raises(WorkspaceError):
        await WorkspaceManager(CommandRunner()).create(repo_path=repo, workspace_id=workspace_id)


@pytest.mark.asyncio
async def test_create_rejects_absolute_workspace_id(tmp_path: Path) -> None:
    repo = await make_repo(tmp_path / "repo")

    with pytest.raises(WorkspaceError):
        await WorkspaceManager(CommandRunner()).create(
            repo_path=repo,
            workspace_id=str(tmp_path / "absolute"),
        )


@pytest.mark.asyncio
async def test_create_rejects_missing_file_and_non_git_repositories(tmp_path: Path) -> None:
    manager = WorkspaceManager(CommandRunner())
    missing = tmp_path / "missing"
    file_path = tmp_path / "file.txt"
    file_path.write_text("content", encoding="utf-8")
    non_git = tmp_path / "non-git"
    non_git.mkdir()

    with pytest.raises(WorkspaceError, match="does not exist"):
        await manager.create(repo_path=missing, workspace_id="run-1")
    with pytest.raises(WorkspaceError, match="not a directory"):
        await manager.create(repo_path=file_path, workspace_id="run-1")
    with pytest.raises(WorkspaceError, match="validate git repository"):
        await manager.create(repo_path=non_git, workspace_id="run-1")


@pytest.mark.asyncio
async def test_create_rejects_missing_base_ref_existing_path_and_existing_branch(
    tmp_path: Path,
) -> None:
    repo = await make_repo(tmp_path / "repo")
    manager = WorkspaceManager(CommandRunner())

    with pytest.raises(WorkspaceError, match="resolve base ref"):
        await manager.create(repo_path=repo, workspace_id="missing-ref", base_ref="missing")

    (repo / ".worktrees" / "path-exists").mkdir(parents=True)
    with pytest.raises(WorkspaceError, match="already exists"):
        await manager.create(repo_path=repo, workspace_id="path-exists")

    await run_git(repo, ["branch", "devconductor/branch-exists"])
    with pytest.raises(WorkspaceError, match="branch already exists"):
        await manager.create(repo_path=repo, workspace_id="branch-exists")


@pytest.mark.asyncio
async def test_duplicate_id_fails_and_different_ids_create_isolated_worktrees(
    tmp_path: Path,
) -> None:
    repo = await make_repo(tmp_path / "repo")
    manager = WorkspaceManager(CommandRunner())

    first = await manager.create(repo_path=repo, workspace_id="run-1")
    second = await manager.create(repo_path=repo, workspace_id="run-2")

    with pytest.raises(WorkspaceError, match="branch already exists|already exists"):
        await manager.create(repo_path=repo, workspace_id="run-1")
    assert first.worktree_path != second.worktree_path
    assert first.branch_name != second.branch_name


@pytest.mark.parametrize("repo_name", ["repo with spaces", "课程 仓库"])
@pytest.mark.asyncio
async def test_create_supports_spaces_chinese_and_non_system_drive_semantics(
    tmp_path: Path,
    repo_name: str,
) -> None:
    repo = await make_repo(tmp_path / repo_name)

    handle = await create_workspace(repo)

    assert handle.worktree_path.exists()
    assert str(handle.worktree_path).startswith(str(tmp_path))


@pytest.mark.asyncio
async def test_collect_changes_for_modified_untracked_deleted_and_staged_files(
    tmp_path: Path,
) -> None:
    repo = await make_repo(tmp_path / "repo")
    handle = await create_workspace(repo)
    (handle.worktree_path / "tracked.txt").write_text("modified\n", encoding="utf-8")
    (handle.worktree_path / "new.txt").write_text("new content\n", encoding="utf-8")
    (handle.worktree_path / "delete-me.txt").unlink()
    (handle.worktree_path / "staged.txt").write_text("staged content\n", encoding="utf-8")
    await run_git(handle.worktree_path, ["add", "staged.txt"])

    changes = await WorkspaceManager(CommandRunner()).collect_changes(handle)

    assert changes.has_changes is True
    assert changes.changed_files == [
        Path("delete-me.txt"),
        Path("new.txt"),
        Path("staged.txt"),
        Path("tracked.txt"),
    ]
    assert "diff --git a/tracked.txt b/tracked.txt" in changes.diff
    assert "diff --git a/new.txt b/new.txt" in changes.diff
    assert "+new content" in changes.diff
    assert "diff --git a/delete-me.txt b/delete-me.txt" in changes.diff
    assert "diff --git a/staged.txt b/staged.txt" in changes.diff


@pytest.mark.asyncio
async def test_collect_changes_does_not_change_real_index_or_status(tmp_path: Path) -> None:
    repo = await make_repo(tmp_path / "repo")
    handle = await create_workspace(repo)
    (handle.worktree_path / "tracked.txt").write_text("unstaged\n", encoding="utf-8")
    (handle.worktree_path / "staged.txt").write_text("staged\n", encoding="utf-8")
    await run_git(handle.worktree_path, ["add", "staged.txt"])
    before = (
        await run_git(handle.worktree_path, ["status", "--porcelain=v1", "-z"])
    ).stdout

    await WorkspaceManager(CommandRunner()).collect_changes(handle)
    after = (await run_git(handle.worktree_path, ["status", "--porcelain=v1", "-z"])).stdout
    indexes = list((repo / ".worktrees" / ".indexes").glob("*.index"))

    assert after == before
    assert indexes == []


@pytest.mark.asyncio
async def test_collect_changes_when_clean_returns_no_changes(tmp_path: Path) -> None:
    repo = await make_repo(tmp_path / "repo")
    handle = await create_workspace(repo)

    changes = await WorkspaceManager(CommandRunner()).collect_changes(handle)

    assert changes.changed_files == []
    assert changes.diff == ""
    assert changes.has_changes is False


@pytest.mark.asyncio
async def test_remove_rejects_dirty_worktree_by_default_and_force_removes_it(
    tmp_path: Path,
) -> None:
    repo = await make_repo(tmp_path / "repo")
    handle = await create_workspace(repo)
    (handle.worktree_path / "tracked.txt").write_text("dirty\n", encoding="utf-8")
    manager = WorkspaceManager(CommandRunner())

    with pytest.raises(WorkspaceError, match="remove worktree"):
        await manager.remove(handle)

    await manager.remove(handle, force=True)
    assert handle.worktree_path.resolve() not in await worktree_paths(repo)


@pytest.mark.asyncio
async def test_remove_keeps_branch_by_default_and_can_delete_matching_branch(
    tmp_path: Path,
) -> None:
    repo = await make_repo(tmp_path / "repo")
    manager = WorkspaceManager(CommandRunner())
    kept = await manager.create(repo_path=repo, workspace_id="kept")
    deleted = await manager.create(repo_path=repo, workspace_id="deleted")

    await manager.remove(kept)
    await manager.remove(deleted, delete_branch=True)

    assert await branch_exists(repo, kept.branch_name)
    assert not await branch_exists(repo, deleted.branch_name)
    assert await branch_exists(repo, "main")


@pytest.mark.asyncio
async def test_remove_refuses_unmanaged_workspace_path_or_branch(tmp_path: Path) -> None:
    repo = await make_repo(tmp_path / "repo")
    handle = await create_workspace(repo)
    manager = WorkspaceManager(CommandRunner())
    bad_path = handle.model_copy(update={"worktree_path": repo})
    bad_branch = handle.model_copy(update={"branch_name": "main"})

    with pytest.raises(WorkspaceError):
        await manager.remove(bad_path, force=True)
    with pytest.raises(WorkspaceError):
        await manager.remove(bad_branch, force=True)


@pytest.mark.asyncio
async def test_workspace_models_json_round_trip_and_reject_unknown_fields(tmp_path: Path) -> None:
    repo = await make_repo(tmp_path / "repo")
    handle = await create_workspace(repo)
    changes = WorkspaceChanges(changed_files=[Path("a.txt"), Path("a.txt")], diff="diff")

    assert WorkspaceHandle.model_validate_json(handle.model_dump_json()) == handle
    assert WorkspaceChanges.model_validate_json(changes.model_dump_json()) == changes
    assert changes.changed_files == [Path("a.txt")]

    with pytest.raises(ValidationError):
        WorkspaceHandle.model_validate({**handle.model_dump(), "model": "codex"})
    with pytest.raises(ValidationError):
        WorkspaceChanges.model_validate({"changed_files": [], "diff": "", "extra": True})
    with pytest.raises(ValidationError):
        WorkspaceChanges(changed_files=[Path("../outside.txt")], diff="")
    with pytest.raises(ValidationError):
        WorkspaceChanges(changed_files=[], diff="diff", has_changes=False)


class FakeRunner:
    def __init__(self, results: list[CommandResult | CommandRunnerError]) -> None:
        self.results = list(results)
        self.calls: list[tuple[list[str], Path, dict[str, str] | None]] = []

    async def run(
        self,
        command: list[str],
        *,
        cwd: Path,
        timeout_seconds: float | None = None,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        self.calls.append((list(command), cwd, dict(env) if env is not None else None))
        result = self.results.pop(0)
        if isinstance(result, CommandRunnerError):
            raise result
        return result


def fake_result(command: list[str], stdout: str = "", exit_code: int | None = 0) -> CommandResult:
    now = datetime(2026, 6, 13, 12, 0, tzinfo=UTC)
    return CommandResult(
        command=command,
        exit_code=exit_code,
        stdout=stdout,
        stderr="",
        started_at=now,
        finished_at=now,
        timed_out=False,
    )


@pytest.mark.asyncio
async def test_create_uses_injected_runner_for_all_git_calls(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    worktree = repo / ".worktrees" / "run-1"
    runner = FakeRunner(
        [
            fake_result(["git", "rev-parse", "--show-toplevel"], stdout=f"{repo}\n"),
            fake_result(["git", "rev-parse", "--verify", "HEAD^{commit}"], stdout="abc123\n"),
            fake_result(["git", "branch", "--list", "devconductor/run-1"], stdout=""),
            fake_result(["git", "worktree", "add"], stdout=""),
            fake_result(["git", "branch", "--list", "devconductor/run-1"], stdout=""),
        ]
    )

    with pytest.raises(WorkspaceError, match="Git did not create"):
        await WorkspaceManager(runner).create(repo_path=repo, workspace_id="run-1")

    assert [call[0][0] for call in runner.calls] == ["git", "git", "git", "git", "git"]
    assert [call[0][1] for call in runner.calls[:4]] == [
        "rev-parse",
        "rev-parse",
        "branch",
        "worktree",
    ]
    assert not worktree.exists()


@pytest.mark.asyncio
async def test_create_failure_cleans_up_created_branch(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runner = FakeRunner(
        [
            fake_result(["git", "rev-parse", "--show-toplevel"], stdout=f"{repo}\n"),
            fake_result(["git", "rev-parse", "--verify", "HEAD^{commit}"], stdout="abc123\n"),
            fake_result(["git", "branch", "--list", "devconductor/run-1"], stdout=""),
            fake_result(["git", "worktree", "add"], stdout=""),
            fake_result(
                ["git", "branch", "--list", "devconductor/run-1"],
                stdout="  devconductor/run-1\n",
            ),
            fake_result(["git", "branch", "-d", "devconductor/run-1"], stdout=""),
        ]
    )

    with pytest.raises(WorkspaceError, match="Git did not create"):
        await WorkspaceManager(runner).create(repo_path=repo, workspace_id="run-1")

    assert ["git", "branch", "-d", "devconductor/run-1"] in [
        call[0] for call in runner.calls
    ]
