"""Single-worker local run coordination."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from backend.app.adapters.base import AgentAdapter
from backend.app.schemas.agent import AgentExecutionRequest, AgentRunStatus
from backend.app.schemas.run import RunReport, RunStatus
from backend.app.schemas.task import TaskSpec
from backend.app.schemas.verification import VerificationSpec, VerificationSummary
from backend.app.schemas.workspace import WorkspaceChanges, WorkspaceHandle


class _WorkspaceManager(Protocol):
    async def create(
        self,
        *,
        repo_path: Path,
        workspace_id: str,
        base_ref: str = "HEAD",
    ) -> WorkspaceHandle: ...

    async def collect_changes(self, workspace: WorkspaceHandle) -> WorkspaceChanges: ...


class _Verifier(Protocol):
    async def verify(
        self,
        specs: list[VerificationSpec],
        *,
        cwd: Path,
        stop_on_failure: bool = False,
    ) -> VerificationSummary: ...


class SingleWorkerCoordinator:
    """Coordinate one task through workspace, agent, diff, and verification steps."""

    def __init__(
        self,
        *,
        workspace_manager: _WorkspaceManager,
        agent_adapter: AgentAdapter,
        verifier: _Verifier,
        run_id_factory: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._workspace_manager = workspace_manager
        self._agent_adapter = agent_adapter
        self._verifier = verifier
        self._run_id_factory = run_id_factory or (lambda: f"run-{uuid4().hex}")
        self._clock = clock or (lambda: datetime.now(UTC))

    async def run(self, task: TaskSpec) -> RunReport:
        """Run a single task and return a reviewable report."""

        run_id = self._run_id_factory()
        started_at = self._utc_now()
        errors: list[str] = []
        extensions: dict[str, object] = {}
        workspace: WorkspaceHandle | None = None
        agent_result = None
        verification_summary: VerificationSummary | None = None
        changed_files: list[Path] = []
        diff = ""
        status = RunStatus.FAILED

        try:
            base_ref = self._base_ref_for(task)
            workspace = await self._workspace_manager.create(
                repo_path=task.repo_path,
                workspace_id=run_id,
                base_ref=base_ref,
            )

            agent_request = self._build_agent_request(task, workspace)
            agent_result = await self._agent_adapter.execute(agent_request)

            try:
                changes = await self._workspace_manager.collect_changes(workspace)
                changed_files = list(changes.changed_files)
                diff = changes.diff
            except Exception as exc:  # noqa: BLE001 - report and preserve prior run facts.
                errors.append(f"Failed to collect workspace changes: {exc}")
                changes = None

            if agent_result.status is not AgentRunStatus.SUCCEEDED:
                errors.extend(agent_result.errors)
                errors.append(f"Agent finished with status {agent_result.status.value}.")
            elif changes is None:
                pass
            elif not changes.has_changes:
                errors.append("Agent completed but produced no code changes.")
            else:
                verification_specs = self._verification_specs_for(task)
                if not verification_specs:
                    extensions["warnings"] = ["No verification commands configured."]
                verification_summary = await self._verifier.verify(
                    verification_specs,
                    cwd=workspace.worktree_path,
                    stop_on_failure=False,
                )
                if verification_summary.required_passed:
                    status = RunStatus.AWAITING_APPROVAL
                else:
                    errors.append("Required verification failed.")

        except (TimeoutError, asyncio.CancelledError):
            status = RunStatus.CANCELLED
            errors.append("Run was cancelled.")
        except Exception as exc:  # noqa: BLE001 - convert orchestration failures into report.
            errors.append(str(exc))

        if status is RunStatus.AWAITING_APPROVAL and errors:
            status = RunStatus.FAILED

        return RunReport(
            run_id=run_id,
            task_id=task.id,
            worker=task.worker,
            status=status,
            started_at=started_at,
            finished_at=self._utc_now(),
            changed_files=changed_files,
            diff=diff,
            verification_results=verification_summary.results if verification_summary else [],
            verification_summary=verification_summary,
            agent_result=agent_result,
            workspace=workspace,
            errors=errors,
            extensions=extensions,
        )

    def _utc_now(self) -> datetime:
        return self._clock().astimezone(UTC)

    @staticmethod
    def _base_ref_for(task: TaskSpec) -> str:
        value = task.extensions.get("base_ref")
        return value if isinstance(value, str) and value.strip() else "HEAD"

    @staticmethod
    def _build_agent_request(task: TaskSpec, workspace: WorkspaceHandle) -> AgentExecutionRequest:
        allowed_files = [f"- {path}" for path in task.constraints.allowed_files]
        if not allowed_files:
            allowed_files = ["- Not specified."]
        forbidden_operations = [
            f"- {operation}" for operation in task.constraints.forbidden_operations
        ]
        prompt = "\n".join(
            [
                "Task objective:",
                task.objective,
                "",
                "Acceptance criteria:",
                *[f"- {criterion}" for criterion in task.acceptance_criteria],
                "",
                "Allowed file scope:",
                *allowed_files,
                "",
                "Forbidden operations:",
                *forbidden_operations,
                "- Do not commit.",
                "- Do not merge.",
                "- Do not push.",
                "",
                "Execution rules:",
                "- The current working directory is an isolated Git worktree.",
                "- Make only the requested code changes.",
                "- Do not repeat the full deterministic verification suite; DevConductor "
                "will run configured verification after implementation.",
                "- Run only focused checks when they are necessary for the change.",
                "- After finishing, return a concise implementation summary only.",
            ]
        )
        return AgentExecutionRequest(
            task_id=task.id,
            prompt=prompt,
            workspace_path=workspace.worktree_path,
            timeout_seconds=float(task.budget.timeout_seconds),
            env=_env_from_extensions(task),
        )

    @staticmethod
    def _verification_specs_for(task: TaskSpec) -> list[VerificationSpec]:
        return [
            VerificationSpec(
                name=f"verification-{index}",
                command=list(command),
                timeout_seconds=float(task.budget.timeout_seconds),
                required=True,
            )
            for index, command in enumerate(task.test_commands, start=1)
        ]


def _env_from_extensions(task: TaskSpec) -> dict[str, str]:
    raw_env = task.extensions.get("env")
    if not isinstance(raw_env, dict):
        return {}
    return {str(key): str(value) for key, value in raw_env.items()}
