# DevConductor

DevConductor is a human-led multi-agent software engineering orchestration platform.

Its goal is to coordinate coding agents such as Codex, Claude Code, and DeepSeek in isolated workspaces, verify their work with deterministic tools, and require human approval before code is accepted.

## Current status

Stage 1: core Python contracts are being introduced.

The first executable milestone remains a local single-worker CLI:

```text
task file
  -> isolated Git worktree
  -> one agent adapter
  -> captured logs and diff
  -> deterministic verification
  -> structured report
  -> human decision
```

## Repository layout

```text
backend/app/       Python application code and vendor-neutral schemas
backend/tests/     Python tests
docs/              Architecture and decision records
frontend/          Reserved for a later web interface
tasks/             Versioned example task specifications
runs/              Local generated run artifacts; ignored by Git
```

## Python setup

Install the project-local environment and development dependencies with `uv`:

```powershell
uv sync --dev
```

Run the configured checks:

```powershell
uv run pytest
uv run ruff check .
uv run mypy backend
```

## Agent instructions

- Codex reads `AGENTS.md`.
- Claude Code reads `CLAUDE.md`, which imports `AGENTS.md`.
- Repository rules should be maintained primarily in `AGENTS.md`.

## Stage 1 contracts

The first implemented contracts are:

1. `TaskSpec`
2. `TaskConstraints`
3. `TaskBudget`
4. `CommandResult`
5. `VerificationResult`
6. `RunReport`

Adapter, command runner, worktree, API, database, frontend, and scheduling behavior are still deferred.

