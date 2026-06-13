"""Verification input and summary contracts."""

from typing import Any

from pydantic import Field, field_validator, model_validator

from backend.app.schemas.base import ContractModel
from backend.app.schemas.command import VerificationResult
from backend.app.schemas.task import _validate_command_arguments, _validate_non_empty_string


class VerificationSpec(ContractModel):
    """A deterministic command-backed verification to execute."""

    name: str
    command: list[str]
    timeout_seconds: float | None = None
    env: dict[str, str] = Field(default_factory=dict)
    required: bool = True

    @field_validator("name")
    @classmethod
    def name_must_not_be_empty(cls, value: str) -> str:
        return _validate_non_empty_string(value, "name")

    @field_validator("command", mode="before")
    @classmethod
    def command_must_be_argument_array(cls, value: Any) -> list[str]:
        return _validate_command_arguments(value)

    @field_validator("timeout_seconds")
    @classmethod
    def timeout_must_be_positive(cls, value: float | None) -> float | None:
        if value is not None and value <= 0:
            raise ValueError("timeout_seconds must be greater than 0")
        return value


class VerificationSummary(ContractModel):
    """Summary of deterministic verification results.

    Overall ``passed`` means every required verification passed. Non-required
    failures are preserved in the result list and failure counts, but do not
    make ``required_passed`` false.
    """

    results: list[VerificationResult] = Field(default_factory=list)
    passed: bool = True
    required_passed: bool = True
    total_count: int = 0
    passed_count: int = 0
    failed_count: int = 0
    timed_out_count: int = 0
    stopped_early: bool = False

    @model_validator(mode="before")
    @classmethod
    def fill_or_validate_counts(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        values = dict(data)
        results = values.get("results", [])
        parsed_results = [
            result
            if isinstance(result, VerificationResult)
            else VerificationResult.model_validate(result)
            for result in results
        ]
        expected = cls._calculate(parsed_results)

        for field_name, expected_value in expected.items():
            supplied = values.get(field_name)
            if supplied is None:
                values[field_name] = expected_value
            elif supplied != expected_value:
                raise ValueError(f"{field_name} is inconsistent with results")
        return values

    @staticmethod
    def from_results(
        results: list[VerificationResult],
        *,
        stopped_early: bool = False,
    ) -> "VerificationSummary":
        return VerificationSummary(results=results, stopped_early=stopped_early)

    @staticmethod
    def _calculate(results: list[VerificationResult]) -> dict[str, int | bool]:
        required_passed = all(result.passed for result in results if result.required)
        passed_count = sum(1 for result in results if result.passed)
        failed_count = len(results) - passed_count
        timed_out_count = sum(
            1
            for result in results
            if result.command_result is not None and result.command_result.timed_out
        )
        return {
            "passed": required_passed,
            "required_passed": required_passed,
            "total_count": len(results),
            "passed_count": passed_count,
            "failed_count": failed_count,
            "timed_out_count": timed_out_count,
        }
