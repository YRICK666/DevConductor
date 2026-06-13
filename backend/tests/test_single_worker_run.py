from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from backend.app.orchestrator import SingleWorkerCoordinator
from backend.app.schemas.agent import (
    AgentExecutionRequest,
    AgentExecutionResult,
    AgentRunStatus,
)
from backend.app.schemas.command import CommandResult, VerificationResult
from backend.app.schemas.run import RunReport, RunStatus
from backend.app.schemas.task import TaskBudget, TaskConstraints, TaskSpec
from backend.app.schemas.verification import VerificationSpec, VerificationSummary
from backend.app.schemas.workspace import WorkspaceChanges, WorkspaceHandle


def instant(seconds: int = 0) -> datetime:
    return datetime(2026, 6, 14, 12, 0, seconds, tzinfo=UTC)


def clock_factory() -> Callable[[], datetime]:
    calls = -1

    def tick() -> datetime:
        nonlocal calls
        calls += 1
        return instant(calls)

    return tick


def task(**overrides: object) -> TaskSpec:
    data: dict[str, object] = {
        "id": "task-1",
        "repo_path": Path("repo"),
        "objective": "Add a feature",
        "worker": "codex",
        "constraints": TaskConstraints(
            allowed_files=[Path("src/app.py")],
            forbidden_operations=["Do not edit secrets"],
        ),
        "acceptance_criteria": ["Feature works", "Tests pass"],
        "test_commands": [["python", "-m", "pytest"]],
        "budget": TaskBudget(max_turns=1, timeout_seconds=30, max_cost_usd=Decimal("0")),
        "extensions": {},
    }
    data.update(overrides)
    return TaskSpec.model_validate(data)


def workspace() -> WorkspaceHandle:
    return WorkspaceHandle(
        workspace_id="run-1",
        repo_path=Path("repo"),
        worktree_path=Path("repo/.worktrees/run-1"),
        branch_name="devconductor/run-1",
        base_ref="HEAD",
        base_commit="abc123",
        created_at=instant(),
    )


def command_result(exit_code: int | None = 0, timed_out: bool = False) -> CommandResult:
    return CommandResult(
        command=["python", "-m", "pytest"],
        exit_code=exit_code,
        stdout="",
        stderr="",
        started_at=instant(),
        finished_at=instant(1),
        timed_out=timed_out,
    )


def agent_result(status: AgentRunStatus = AgentRunStatus.SUCCEEDED) -> AgentExecutionResult:
    return AgentExecutionResult(
        agent_name="fake-agent",
        task_id="task-1",
        status=status,
        started_at=instant(),
        finished_at=instant(1),
        final_output="Implemented changes." if status is AgentRunStatus.SUCCEEDED else None,
        errors=[] if status is AgentRunStatus.SUCCEEDED else ["agent failed"],
    )


def verification_summary(passed: bool = True) -> VerificationSummary:
    result = VerificationResult(
        name="verification-1",
        command_result=command_result(0 if passed else 1),
        passed=passed,
        required=True,
    )
    return VerificationSummary.from_results([result])


class FakeWorkspaceManager:
    def __init__(
        self,
        *,
        changes: WorkspaceChanges | Exception | None = None,
        create_error: Exception | None = None,
    ) -> None:
        self.handle = workspace()
        self.changes = changes or WorkspaceChanges(
            changed_files=[Path("src/app.py")],
            diff="diff from workspace",
        )
        self.create_error = create_error
        self.create_calls: list[tuple[Path, str, str]] = []
        self.collect_calls: list[WorkspaceHandle] = []
        self.remove_calls = 0

    async def create(
        self,
        *,
        repo_path: Path,
        workspace_id: str,
        base_ref: str = "HEAD",
    ) -> WorkspaceHandle:
        self.create_calls.append((repo_path, workspace_id, base_ref))
        if self.create_error is not None:
            raise self.create_error
        return self.handle

    async def collect_changes(self, workspace: WorkspaceHandle) -> WorkspaceChanges:
        self.collect_calls.append(workspace)
        if isinstance(self.changes, Exception):
            raise self.changes
        return self.changes

    async def remove(self, workspace: WorkspaceHandle, *, force: bool = False) -> None:
        self.remove_calls += 1


class FakeAgentAdapter:
    name = "fake-agent"

    def __init__(self, result: AgentExecutionResult | None = None) -> None:
        self.result = result or agent_result()
        self.requests: list[AgentExecutionRequest] = []

    async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult:
        self.requests.append(request)
        return self.result


class FakeVerifier:
    def __init__(self, summary: VerificationSummary | None = None) -> None:
        self.summary = summary or verification_summary()
        self.calls: list[tuple[list[str], Path]] = []

    async def verify(
        self,
        specs: list[VerificationSpec],
        *,
        cwd: Path,
        stop_on_failure: bool = False,
    ) -> VerificationSummary:
        self.calls.append(([spec.name for spec in specs], cwd))
        return self.summary if specs else VerificationSummary.from_results([])


def coordinator(
    workspace_manager: FakeWorkspaceManager | None = None,
    agent: FakeAgentAdapter | None = None,
    verifier: FakeVerifier | None = None,
) -> SingleWorkerCoordinator:
    return SingleWorkerCoordinator(
        workspace_manager=workspace_manager or FakeWorkspaceManager(),
        agent_adapter=agent or FakeAgentAdapter(),
        verifier=verifier or FakeVerifier(),
        run_id_factory=lambda: "run-1",
        clock=clock_factory(),
    )


@pytest.mark.asyncio
async def test_successful_run_reaches_awaiting_approval_and_keeps_review_data() -> None:
    workspace_manager = FakeWorkspaceManager()
    agent = FakeAgentAdapter()
    verifier = FakeVerifier()

    report = await coordinator(workspace_manager, agent, verifier).run(task())

    assert report.status is RunStatus.AWAITING_APPROVAL
    assert workspace_manager.create_calls == [(Path("repo"), "run-1", "HEAD")]
    assert agent.requests[0].workspace_path == workspace().worktree_path
    assert "Add a feature" in agent.requests[0].prompt
    assert "Feature works" in agent.requests[0].prompt
    assert "Do not commit" in agent.requests[0].prompt
    assert "Do not merge" in agent.requests[0].prompt
    assert "Do not push" in agent.requests[0].prompt
    assert "Do not repeat the full deterministic verification suite" in agent.requests[0].prompt
    assert verifier.calls == [(["verification-1"], workspace().worktree_path)]
    assert report.agent_result == agent.result
    assert report.workspace == workspace_manager.handle
    assert report.verification_summary == verifier.summary
    assert report.changed_files == [Path("src/app.py")]
    assert report.diff == "diff from workspace"
    assert workspace_manager.remove_calls == 0


@pytest.mark.parametrize(
    "status",
    [
        AgentRunStatus.FAILED,
        AgentRunStatus.TIMED_OUT,
        AgentRunStatus.STARTUP_FAILED,
        AgentRunStatus.INVALID_OUTPUT,
    ],
)
@pytest.mark.asyncio
async def test_agent_non_success_fails_but_still_collects_changes(
    status: AgentRunStatus,
) -> None:
    workspace_manager = FakeWorkspaceManager()
    agent = FakeAgentAdapter(agent_result(status))
    verifier = FakeVerifier()

    report = await coordinator(workspace_manager, agent, verifier).run(task())

    assert report.status is RunStatus.FAILED
    assert workspace_manager.collect_calls == [workspace()]
    assert report.changed_files == [Path("src/app.py")]
    assert verifier.calls == []


@pytest.mark.asyncio
async def test_agent_success_without_changes_fails() -> None:
    workspace_manager = FakeWorkspaceManager(changes=WorkspaceChanges())

    report = await coordinator(workspace_manager).run(task())

    assert report.status is RunStatus.FAILED
    assert "Agent completed but produced no code changes." in report.errors
    assert report.verification_summary is None


@pytest.mark.asyncio
async def test_verification_failure_fails_and_preserves_prior_information() -> None:
    verifier = FakeVerifier(verification_summary(False))

    report = await coordinator(verifier=verifier).run(task())

    assert report.status is RunStatus.FAILED
    assert report.agent_result is not None
    assert report.workspace is not None
    assert report.changed_files == [Path("src/app.py")]
    assert report.verification_summary is verifier.summary
    assert "Required verification failed." in report.errors


@pytest.mark.asyncio
async def test_empty_verification_commands_are_recorded_but_can_await_approval() -> None:
    verifier = FakeVerifier()

    report = await coordinator(verifier=verifier).run(task(test_commands=[]))

    assert report.status is RunStatus.AWAITING_APPROVAL
    assert report.verification_summary == VerificationSummary.from_results([])
    assert report.extensions == {"warnings": ["No verification commands configured."]}


@pytest.mark.asyncio
async def test_diff_collection_failure_is_recorded() -> None:
    workspace_manager = FakeWorkspaceManager(changes=RuntimeError("diff failed"))

    report = await coordinator(workspace_manager).run(task())

    assert report.status is RunStatus.FAILED
    assert report.agent_result is not None
    assert report.workspace is not None
    assert report.changed_files == []
    assert "Failed to collect workspace changes: diff failed" in report.errors


@pytest.mark.asyncio
async def test_workspace_creation_failure_is_recorded_without_agent_call() -> None:
    workspace_manager = FakeWorkspaceManager(create_error=RuntimeError("create failed"))
    agent = FakeAgentAdapter()

    report = await coordinator(workspace_manager, agent).run(task())

    assert report.status is RunStatus.FAILED
    assert report.workspace is None
    assert report.agent_result is None
    assert agent.requests == []
    assert "create failed" in report.errors


@pytest.mark.asyncio
async def test_task_spec_is_not_modified_and_prompt_does_not_leak_env_value() -> None:
    original = task(extensions={"env": {"PRIVATE_TEST_VALUE": "do-not-print"}})
    before = original.model_dump()
    agent = FakeAgentAdapter()

    await coordinator(agent=agent).run(original)

    assert original.model_dump() == before
    assert "do-not-print" not in agent.requests[0].prompt
    assert agent.requests[0].env == {"PRIVATE_TEST_VALUE": "do-not-print"}


@pytest.mark.asyncio
async def test_changed_files_and_diff_come_from_workspace_not_agent_text() -> None:
    agent = FakeAgentAdapter(
        AgentExecutionResult(
            agent_name="fake-agent",
            task_id="task-1",
            status=AgentRunStatus.SUCCEEDED,
            started_at=instant(),
            finished_at=instant(1),
            final_output="Changed other.py with diff from agent",
        )
    )

    report = await coordinator(agent=agent).run(task())

    assert report.changed_files == [Path("src/app.py")]
    assert report.diff == "diff from workspace"


@pytest.mark.asyncio
async def test_run_report_time_order_and_json_round_trip() -> None:
    report = await coordinator().run(task())

    assert report.finished_at is not None
    assert report.started_at <= report.finished_at
    assert RunReport.model_validate_json(report.model_dump_json()) == report
