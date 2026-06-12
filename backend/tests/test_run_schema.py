from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.schemas.command import CommandResult, VerificationResult
from backend.app.schemas.run import RunReport, RunStatus


def started_at() -> datetime:
    return datetime(2026, 6, 12, 11, 0, tzinfo=UTC)


def command_result() -> CommandResult:
    start = started_at()
    return CommandResult(
        command=["python", "-m", "pytest"],
        exit_code=0,
        stdout="",
        stderr="",
        started_at=start,
        finished_at=start + timedelta(seconds=1),
        timed_out=False,
    )


def verification_result() -> VerificationResult:
    return VerificationResult(name="pytest", command_result=command_result(), passed=True)


def valid_run_report(**overrides: object) -> RunReport:
    start = started_at()
    data: dict[str, object] = {
        "run_id": "run-1",
        "task_id": "task-1",
        "worker": "codex",
        "status": RunStatus.AWAITING_APPROVAL,
        "started_at": start,
        "finished_at": start + timedelta(seconds=2),
        "changed_files": [Path("backend/app/schemas/task.py")],
        "diff": "diff --git ...",
        "verification_results": [verification_result()],
        "errors": [],
        "extensions": {},
    }
    data.update(overrides)
    return RunReport.model_validate(data)


def test_invalid_run_status_is_rejected() -> None:
    with pytest.raises(ValidationError):
        valid_run_report(status="merged")


def test_run_report_rejects_finished_before_started() -> None:
    with pytest.raises(ValidationError):
        valid_run_report(finished_at=started_at() - timedelta(seconds=1))


def test_pending_and_running_allow_missing_finished_at() -> None:
    pending = valid_run_report(status=RunStatus.PENDING, finished_at=None)
    running = valid_run_report(status=RunStatus.RUNNING, finished_at=None)

    assert pending.finished_at is None
    assert running.finished_at is None


@pytest.mark.parametrize("field", ["run_id", "task_id", "worker"])
def test_run_report_required_text_fields_reject_blank(field: str) -> None:
    with pytest.raises(ValidationError):
        valid_run_report(**{field: "   "})


def test_run_report_json_serialization_round_trip() -> None:
    report = valid_run_report()

    loaded = RunReport.model_validate_json(report.model_dump_json())

    assert loaded == report


def test_run_report_extensions_store_vendor_information() -> None:
    report = valid_run_report(extensions={"claude": {"session_id": "abc"}})

    assert report.extensions == {"claude": {"session_id": "abc"}}


def test_run_report_rejects_unknown_top_level_fields() -> None:
    with pytest.raises(ValidationError):
        valid_run_report(codex_model="gpt-5-codex")


def test_run_report_does_not_default_to_accepted() -> None:
    report = valid_run_report(status=RunStatus.SUCCEEDED)

    assert report.status is RunStatus.SUCCEEDED


def test_mutable_defaults_are_not_shared_between_run_reports() -> None:
    first = RunReport(
        run_id="run-1",
        task_id="task-1",
        worker="codex",
        status=RunStatus.PENDING,
        started_at=started_at(),
    )
    second = RunReport(
        run_id="run-2",
        task_id="task-2",
        worker="codex",
        status=RunStatus.PENDING,
        started_at=started_at(),
    )

    first.changed_files.append(Path("README.md"))
    first.verification_results.append(verification_result())
    first.errors.append("failed")
    first.extensions["codex"] = {"model": "gpt-5-codex"}

    assert second.changed_files == []
    assert second.verification_results == []
    assert second.errors == []
    assert second.extensions == {}
