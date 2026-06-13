# DevConductor

DevConductor is a human-led multi-agent software engineering orchestration platform.

Its goal is to coordinate coding agents such as Codex, Claude Code, and DeepSeek in isolated workspaces, verify their work with deterministic tools, and require human approval before code is accepted.

## Current status

Stage 6: the local single-worker run loop is being introduced.

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

## CLI usage

Run a local task file with the default Codex adapter:

```powershell
uv run devconductor run tasks/example-task.yaml --adapter codex --output runs/report.json
```

Use `--dry-run` to read and validate the task file without creating a worktree,
calling an agent, or running verification:

```powershell
uv run devconductor run tasks/example-task.yaml --dry-run
```

The example task uses a placeholder repository path. Replace it with a small
playground Git repository before running a real agent.

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

## Stage 3 verifier

The deterministic `Verifier` accepts structured `VerificationSpec` commands,
runs them in order through `CommandRunner`, and returns a `VerificationSummary`.
It treats a verification as passed only when the process exits with code `0` and
does not time out. An empty verification list returns an empty passing summary.

The verifier can either continue after failures or stop after the first failed
required verification. Non-required failures are preserved in the summary but do
not make `required_passed` false.

## Stage 4 workspace manager

The `WorkspaceManager` creates isolated Git worktrees under
`.worktrees/<workspace_id>/` on branches named `devconductor/<workspace_id>`.
It resolves the requested base ref to an immutable commit before creating the
worktree, so uncommitted changes in the main repository are not copied into the
agent workspace.

Workspace changes are collected from Git status and a temporary Git index, which
allows diffs to include untracked file contents without changing the worktree's
real staged or unstaged state. Removal is explicit; dirty worktrees are rejected
unless `force=True`, and workspace branches are kept unless `delete_branch=True`.

## Stage 5 Codex adapter

Agent adapters implement a shared `AgentAdapter` interface. The vendor-neutral
request and result models capture the task ID, prompt, workspace path, process
status, final agent message, session ID, token usage, command facts, and errors.

`CodexAdapter` invokes the local Codex CLI through `CommandRunner` as
`codex --ask-for-approval never --sandbox workspace-write exec --json --ephemeral -`.
The prompt is sent through standard input instead of command-line arguments. The
adapter parses JSONL output, extracts the last agent message as advisory output,
and does not treat agent text as verification or approval.

## Stage 6 single-worker run

`SingleWorkerCoordinator` connects `TaskSpec`, `WorkspaceManager`,
`AgentAdapter`, `WorkspaceChanges`, `Verifier`, and `RunReport` into one local
run. A successful implementation plus required verification ends in
`awaiting_approval`, preserving the worktree for human review. Failures are
reported as `failed` or `cancelled`; the coordinator never commits, merges,
pushes, or accepts changes.

Manual Codex smoke test:

1. Create a small throwaway Git repository outside this project.
2. Prepare a TaskSpec that points at that repository and asks for one simple change.
3. Configure any required shell environment for your Codex CLI session.
4. Run `uv run devconductor run <task-file> --adapter codex --output runs/report.json`.
5. Inspect the generated `.worktrees/<run_id>/`, diff, verification results, and JSON report.
6. Confirm no commit, merge, or push happened automatically.

Claude, DeepSeek, Gemini, API, database, frontend, approval policy, and scheduling behavior are still deferred.
