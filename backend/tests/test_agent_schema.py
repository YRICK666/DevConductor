from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.adapters.base import AgentAdapter
from backend.app.schemas.agent import (
    AgentExecutionRequest,
    AgentExecutionResult,
    AgentModelProfile,
    AgentRunStatus,
    AgentUsage,
)


def request(**overrides: object) -> AgentExecutionRequest:
    data: dict[str, object] = {
        "task_id": "task-1",
        "prompt": "Implement the task",
        "workspace_path": Path("G:/AI-Workstation/repo/.worktrees/run-1"),
        "timeout_seconds": 30.0,
        "env": {},
        "extensions": {},
    }
    data.update(overrides)
    return AgentExecutionRequest.model_validate(data)


def result(**overrides: object) -> AgentExecutionResult:
    started_at = datetime(2026, 6, 14, 12, 0, tzinfo=UTC)
    data: dict[str, object] = {
        "agent_name": "test-agent",
        "task_id": "task-1",
        "status": AgentRunStatus.SUCCEEDED,
        "started_at": started_at,
        "finished_at": started_at + timedelta(seconds=1),
        "final_output": "done",
        "session_id": "session-1",
        "profile": AgentModelProfile.MINI,
        "reported_model": "gpt-test-model",
        "model_metadata": {"provider": "openai"},
        "usage": AgentUsage(input_tokens=1),
        "elapsed_seconds": 1.0,
        "attempt_count": 1,
        "command_result": None,
        "errors": [],
        "extensions": {},
    }
    data.update(overrides)
    return AgentExecutionResult.model_validate(data)


def test_agent_execution_request_valid_creation() -> None:
    created = request()

    assert created.task_id == "task-1"
    assert created.prompt == "Implement the task"


def test_agent_execution_request_rejects_blank_task_id() -> None:
    with pytest.raises(ValidationError):
        request(task_id="   ")


def test_agent_execution_request_rejects_blank_prompt() -> None:
    with pytest.raises(ValidationError):
        request(prompt="   ")


def test_agent_execution_request_rejects_invalid_timeout() -> None:
    with pytest.raises(ValidationError):
        request(timeout_seconds=0)


def test_agent_request_mutable_defaults_are_not_shared() -> None:
    first = AgentExecutionRequest(
        task_id="one",
        prompt="prompt",
        workspace_path=Path("repo"),
    )
    second = AgentExecutionRequest(
        task_id="two",
        prompt="prompt",
        workspace_path=Path("repo"),
    )

    first.env["VALUE"] = "one"
    first.extensions["adapter"] = "test"

    assert second.env == {}
    assert second.extensions == {}


def test_agent_usage_rejects_negative_values() -> None:
    with pytest.raises(ValidationError):
        AgentUsage(input_tokens=-1)


def test_agent_execution_result_rejects_invalid_time_order() -> None:
    started_at = datetime(2026, 6, 14, 12, 0, tzinfo=UTC)

    with pytest.raises(ValidationError):
        result(started_at=started_at, finished_at=started_at - timedelta(seconds=1))


def test_agent_execution_result_json_round_trip_and_unknown_fields() -> None:
    created = result()

    assert AgentExecutionResult.model_validate_json(created.model_dump_json()) == created
    assert created.profile is AgentModelProfile.MINI
    assert created.reported_model == "gpt-test-model"
    assert created.elapsed_seconds == 1.0
    assert created.attempt_count == 1
    with pytest.raises(ValidationError):
        request(model="codex")
    with pytest.raises(ValidationError):
        result(model="codex")


class TestAdapter:
    @property
    def name(self) -> str:
        return "test"

    async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult:
        return result(task_id=request.task_id)


def test_agent_adapter_protocol_can_be_satisfied() -> None:
    adapter: AgentAdapter = TestAdapter()

    assert adapter.name == "test"
