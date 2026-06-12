from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from backend.app.schemas.command import CommandResult, VerificationResult


def now() -> datetime:
    return datetime(2026, 6, 12, 10, 0, tzinfo=UTC)


def valid_command_result(**overrides: object) -> CommandResult:
    started_at = now()
    data: dict[str, object] = {
        "command": ["python", "-m", "pytest"],
        "exit_code": 0,
        "stdout": "ok",
        "stderr": "",
        "started_at": started_at,
        "finished_at": started_at + timedelta(seconds=1),
        "timed_out": False,
    }
    data.update(overrides)
    return CommandResult.model_validate(data)


def test_command_result_rejects_empty_command() -> None:
    with pytest.raises(ValidationError):
        valid_command_result(command=[])


def test_command_result_rejects_blank_argument() -> None:
    with pytest.raises(ValidationError):
        valid_command_result(command=["python", "   "])


def test_command_result_rejects_finished_before_started() -> None:
    with pytest.raises(ValidationError):
        valid_command_result(finished_at=now() - timedelta(seconds=1))


def test_exit_code_may_be_none_when_timed_out() -> None:
    result = valid_command_result(exit_code=None, timed_out=True)

    assert result.exit_code is None
    assert result.timed_out is True


def test_verification_result_requires_name() -> None:
    with pytest.raises(ValidationError):
        VerificationResult(
            name="   ",
            command_result=valid_command_result(),
            passed=False,
        )


def test_command_result_rejects_unknown_top_level_fields() -> None:
    with pytest.raises(ValidationError):
        valid_command_result(agent_claim="tests passed")


def test_verification_result_json_round_trip() -> None:
    verification = VerificationResult(
        name="pytest",
        command_result=valid_command_result(),
        passed=True,
        details=None,
    )

    loaded = VerificationResult.model_validate_json(verification.model_dump_json())

    assert loaded == verification
