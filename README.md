# DevConductor

DevConductor is a human-led multi-agent software engineering orchestration platform.

Its goal is to coordinate coding agents such as Codex, Claude Code, and DeepSeek in isolated workspaces, verify their work with deterministic tools, and require human approval before code is accepted.

## Current status

Stage 2: controlled local command execution is being introduced.

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

## Stage 2 command runner

The controlled `CommandRunner` executes local commands from argument arrays with
`asyncio.create_subprocess_exec`, captures stdout and stderr, records real exit
codes, supports working directories, applies environment overrides on top of the
inherited environment, and returns `CommandResult`.

Timeout handling reliably terminates the directly started process. Full
cross-platform process-tree termination is intentionally deferred.

Adapter, worktree, API, database, frontend, approval policy, and scheduling behavior are still deferred.
