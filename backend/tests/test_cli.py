from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from backend.app import cli
from backend.app.schemas.agent import AgentModelProfile
from backend.app.schemas.run import RunReport, RunStatus


def task_payload(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "id": "task-1",
        "repo_path": "repo",
        "objective": "Do the thing",
        "worker": "codex",
        "constraints": {},
        "acceptance_criteria": ["It works"],
        "test_commands": [["python", "-m", "pytest"]],
        "budget": {"max_turns": 1, "timeout_seconds": 30, "max_cost_usd": "0"},
        "extensions": {},
    }
    data.update(overrides)
    return data


def write_task(path: Path, **overrides: object) -> Path:
    path.write_text(json.dumps(task_payload(**overrides)), encoding="utf-8")
    return path


def report(status: RunStatus = RunStatus.AWAITING_APPROVAL) -> RunReport:
    return RunReport(
        run_id="run-1",
        task_id="task-1",
        worker="codex",
        status=status,
        started_at=datetime(2026, 6, 14, 12, 0, tzinfo=UTC),
        finished_at=datetime(2026, 6, 14, 12, 0, 1, tzinfo=UTC),
    )


def test_cli_dry_run_reads_task_without_running(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    task_file = write_task(tmp_path / "task.json")

    async def forbidden_run(task: object) -> RunReport:
        raise AssertionError("dry-run must not execute")

    monkeypatch.setattr(cli, "_run_task", forbidden_run)

    exit_code = cli.main(["run", str(task_file), "--dry-run"])

    assert exit_code == 0


def test_cli_rejects_invalid_task_file(tmp_path: Path) -> None:
    task_file = tmp_path / "bad.json"
    task_file.write_text("{}", encoding="utf-8")

    assert cli.main(["run", str(task_file), "--dry-run"]) == 2


def test_cli_rejects_unknown_adapter(tmp_path: Path) -> None:
    task_file = write_task(tmp_path / "task.json")

    assert cli.main(["run", str(task_file), "--adapter", "unknown", "--dry-run"]) == 2


def test_cli_normal_run_writes_report_and_returns_zero(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    task_file = write_task(tmp_path / "task.json")
    output = tmp_path / "report.json"

    async def fake_run(
        task: object,
        profile: AgentModelProfile = AgentModelProfile.MINI,
    ) -> RunReport:
        assert profile is AgentModelProfile.MINI
        return report()

    monkeypatch.setattr(cli, "_run_task", fake_run)

    exit_code = cli.main(["run", str(task_file), "--output", str(output)])

    assert exit_code == 0
    loaded = RunReport.model_validate_json(output.read_text(encoding="utf-8"))
    assert loaded.status is RunStatus.AWAITING_APPROVAL


def test_cli_accepts_standard_profile_for_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    task_file = write_task(tmp_path / "task.json")
    seen_profiles: list[AgentModelProfile] = []

    async def fake_run(
        task: object,
        profile: AgentModelProfile = AgentModelProfile.MINI,
    ) -> RunReport:
        seen_profiles.append(profile)
        return report()

    monkeypatch.setattr(cli, "_run_task", fake_run)

    assert cli.main(["run", str(task_file), "--profile", "standard"]) == 0
    assert seen_profiles == [AgentModelProfile.STANDARD]


def test_cli_failed_report_returns_non_zero(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    task_file = write_task(tmp_path / "task.json")

    async def fake_run(
        task: object,
        profile: AgentModelProfile = AgentModelProfile.MINI,
    ) -> RunReport:
        return report(RunStatus.FAILED)

    monkeypatch.setattr(cli, "_run_task", fake_run)

    assert cli.main(["run", str(task_file)]) == 1


def test_cli_rejects_unknown_profile(tmp_path: Path) -> None:
    task_file = write_task(tmp_path / "task.json")

    assert cli.main(["run", str(task_file), "--profile", "global-gpt-5.5"]) == 2


def test_cli_loads_example_yaml_task() -> None:
    loaded = cli.load_task_file(Path("tasks/example-task.yaml"))

    assert loaded.id == "example-task"
    assert loaded.worker == "codex"
    assert loaded.test_commands == [["python", "-c", "print('replace with project checks')"]]
