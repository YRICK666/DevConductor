"""Local command line interface for DevConductor."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from backend.app.adapters import CodexAdapter
from backend.app.execution import CommandRunner
from backend.app.orchestrator import SingleWorkerCoordinator
from backend.app.schemas.run import RunReport, RunStatus
from backend.app.schemas.task import TaskSpec
from backend.app.verifier import Verifier
from backend.app.workspace import WorkspaceManager


def main(argv: list[str] | None = None) -> int:
    """Run the DevConductor CLI."""

    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        return _run_command(args)
    parser.print_help()
    return 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="devconductor")
    subparsers = parser.add_subparsers(dest="command")
    run_parser = subparsers.add_parser("run", help="Run one task file")
    run_parser.add_argument("task_file", type=Path)
    run_parser.add_argument("--adapter", default="codex")
    run_parser.add_argument("--output", type=Path)
    run_parser.add_argument("--dry-run", action="store_true")
    return parser


def _run_command(args: argparse.Namespace) -> int:
    try:
        task = load_task_file(args.task_file)
    except (OSError, ValueError, ValidationError) as exc:
        print(f"Failed to read task file: {exc}", file=sys.stderr)
        return 2

    if args.adapter != "codex":
        print(f"Unknown adapter: {args.adapter}", file=sys.stderr)
        return 2

    if args.dry_run:
        _print_dry_run(task, args.adapter)
        return 0

    report = asyncio.run(_run_task(task))
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    print(
        f"run_id={report.run_id} status={report.status.value} "
        f"changed_files={len(report.changed_files)} errors={len(report.errors)}"
    )
    return 0 if report.status is RunStatus.AWAITING_APPROVAL else 1


async def _run_task(task: TaskSpec) -> RunReport:
    command_runner = CommandRunner()
    coordinator = SingleWorkerCoordinator(
        workspace_manager=WorkspaceManager(command_runner),
        agent_adapter=CodexAdapter(command_runner),
        verifier=Verifier(command_runner),
    )
    return await coordinator.run(task)


def load_task_file(path: Path) -> TaskSpec:
    """Load a JSON task file or a small YAML subset into a TaskSpec."""

    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
    else:
        data = _parse_simple_yaml(text)
    return TaskSpec.model_validate(data)


def _parse_simple_yaml(text: str) -> dict[str, object]:
    result: dict[str, object] = {}
    current_list_key: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("- ") and current_list_key is not None:
            value = line[2:].strip()
            current = result.setdefault(current_list_key, [])
            if not isinstance(current, list):
                raise ValueError(f"Invalid YAML list for {current_list_key}")
            current.append(_parse_yaml_scalar_or_list(value))
            continue

        current_list_key = None
        if ":" not in line:
            raise ValueError(f"Unsupported YAML line: {raw_line}")
        key, raw_value = line.split(":", 1)
        value = raw_value.strip()
        if not value:
            result[key.strip()] = []
            current_list_key = key.strip()
        else:
            result[key.strip()] = _parse_yaml_scalar_or_list(value)

    if "budget" not in result:
        result["budget"] = {
            "max_turns": result.pop("budget_max_turns", 1),
            "timeout_seconds": result.pop("budget_timeout_seconds", 300),
            "max_cost_usd": result.pop("budget_max_cost_usd", "0"),
        }
    if "constraints" not in result:
        result["constraints"] = {
            "allowed_files": result.pop("constraints_allowed_files", []),
            "forbidden_operations": result.pop("constraints_forbidden_operations", []),
        }
    return result


def _parse_yaml_scalar_or_list(value: str) -> object:
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_strip_quotes(part.strip()) for part in inner.split(",")]
    if value in {"true", "false"}:
        return value == "true"
    try:
        return int(value)
    except ValueError:
        return _strip_quotes(value)


def _strip_quotes(value: str) -> str:
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    return value


def _print_dry_run(task: TaskSpec, adapter: str) -> None:
    print(f"Task: {task.id}")
    print(f"Repository: {task.repo_path}")
    print(f"Worker: {task.worker}")
    print(f"Adapter: {adapter}")
    print(f"Verification commands: {len(task.test_commands)}")
    print(
        "Budget: "
        f"turns={task.budget.max_turns} "
        f"timeout_seconds={task.budget.timeout_seconds} "
        f"max_cost_usd={task.budget.max_cost_usd}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
