from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.schemas.task import TaskBudget, TaskConstraints, TaskSpec


def valid_budget() -> TaskBudget:
    return TaskBudget(max_turns=3, timeout_seconds=60, max_cost_usd=Decimal("1.25"))


def valid_task(**overrides: object) -> TaskSpec:
    data: dict[str, object] = {
        "id": "task-1",
        "repo_path": Path("G:/AI-Workstation/dev conductor"),
        "objective": "Add schemas",
        "worker": "codex",
        "constraints": TaskConstraints(),
        "acceptance_criteria": ["Schemas validate inputs"],
        "test_commands": [["python", "-m", "pytest"]],
        "budget": valid_budget(),
        "extensions": {},
    }
    data.update(overrides)
    return TaskSpec.model_validate(data)


def test_valid_task_spec_creation() -> None:
    task = valid_task()

    assert task.id == "task-1"
    assert task.test_commands == [["python", "-m", "pytest"]]


@pytest.mark.parametrize("field", ["id", "objective", "worker"])
def test_required_text_fields_reject_blank(field: str) -> None:
    with pytest.raises(ValidationError):
        valid_task(**{field: "   "})


def test_acceptance_criteria_must_not_be_empty() -> None:
    with pytest.raises(ValidationError):
        valid_task(acceptance_criteria=[])


def test_acceptance_criteria_items_must_not_be_blank() -> None:
    with pytest.raises(ValidationError):
        valid_task(acceptance_criteria=["   "])


def test_constraints_default_to_no_network_or_external_paths() -> None:
    constraints = TaskConstraints()

    assert constraints.allow_network is False
    assert constraints.allow_repo_external_paths is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_turns", 0),
        ("timeout_seconds", 0),
        ("max_cost_usd", Decimal("-0.01")),
    ],
)
def test_budget_rejects_invalid_limits(field: str, value: object) -> None:
    data: dict[str, object] = {
        "max_turns": 1,
        "timeout_seconds": 1,
        "max_cost_usd": Decimal("0"),
    }
    data[field] = value

    with pytest.raises(ValidationError):
        TaskBudget.model_validate(data)


def test_task_json_serialization_round_trip() -> None:
    task = valid_task()

    loaded = TaskSpec.model_validate_json(task.model_dump_json())

    assert loaded == task


def test_windows_chinese_path_with_spaces_is_preserved() -> None:
    repo_path = Path("G:/AI-Workstation/课程 资料/repo")

    task = valid_task(repo_path=repo_path)

    assert task.repo_path == repo_path


def test_extensions_store_vendor_specific_information() -> None:
    task = valid_task(extensions={"codex": {"model": "gpt-5-codex"}})

    assert task.extensions == {"codex": {"model": "gpt-5-codex"}}


def test_unknown_top_level_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        valid_task(codex_model="gpt-5-codex")


def test_test_commands_keep_argument_array_structure() -> None:
    task = valid_task(test_commands=[["python", "-m", "pytest"], ["ruff", "check", "."]])

    assert task.test_commands[0] == ["python", "-m", "pytest"]
    assert task.test_commands[1] == ["ruff", "check", "."]


def test_test_commands_reject_shell_command_string() -> None:
    with pytest.raises(ValidationError):
        valid_task(test_commands=["python -m pytest"])


def test_mutable_defaults_are_not_shared_between_instances() -> None:
    first_constraints = TaskConstraints()
    second_constraints = TaskConstraints()
    first_constraints.allowed_files.append(Path("README.md"))
    first_constraints.forbidden_operations.append("push")

    first_task = valid_task(test_commands=[], extensions={})
    second_task = valid_task(test_commands=[], extensions={})
    first_task.test_commands.append(["python", "-m", "pytest"])
    first_task.extensions["codex"] = {"model": "gpt-5-codex"}

    assert second_constraints.allowed_files == []
    assert second_constraints.forbidden_operations == []
    assert second_task.test_commands == []
    assert second_task.extensions == {}
