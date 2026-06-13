# Architecture

## Product boundary

DevConductor orchestrates external coding agents. It does not replace them and does not trust their textual claims as verification.

## Core principles

1. Human-controlled acceptance
2. Isolated execution
3. Vendor-neutral core contracts
4. Deterministic verification
5. Complete, reviewable run records
6. Small local-first milestones

## Planned executable flow

```text
TaskSpec
  -> Orchestrator
  -> WorktreeManager
  -> AgentAdapter
  -> CommandRunner
  -> DiffCollector
  -> Verifier
  -> RunReport
  -> Human approval
```

## Planned component boundaries

### Orchestrator

Owns task state and sequencing. It does not contain vendor-specific CLI arguments.

### Agent adapters

Translate a vendor-neutral execution request into a Codex, Claude Code, or DeepSeek process invocation.

### Workspace

Creates and removes isolated Git worktrees under `.worktrees/<workspace_id>/`,
records the requested base ref and resolved base commit, and collects changed
files and diffs.

The Stage 4 implementation creates branches named
`devconductor/<workspace_id>`. Main-repository uncommitted changes do not block
workspace creation and are not copied into the managed worktree because creation
uses the resolved base commit.

Diff collection uses Git status plus a temporary `GIT_INDEX_FILE` under
`.worktrees/.indexes/`, so untracked file contents can be included in the diff
without changing the worktree's real index, staged state, or unstaged state.
Removal is explicit and conservative: dirty worktrees require `force=True`, and
workspace branches are only deleted when requested.

### Command runner

Runs local commands through `asyncio.create_subprocess_exec` with argument arrays,
timeout handling, working-directory support, inherited environment plus explicit
overrides, output capture, and structured `CommandResult` records.

The Stage 2 implementation does not approve commands or enforce allow/deny
policies. It reliably cleans up the directly started process on timeout; full
cross-platform process-tree termination is deferred.

### Verifier

Runs deterministic verification specs in order through `CommandRunner`. It maps
real command results to `VerificationResult` records and summarizes them in a
`VerificationSummary`.

A verification passes only when the command exits with code `0` and does not
time out. Required verification failures make the summary fail; optional
verification failures remain recorded without making `required_passed` false.
An empty verification list returns an empty passing summary.

A model's statement that tests passed is never accepted as proof.

### Schemas

Define task input, agent execution request, command result, verification result, and final run report.

The current implemented schema slice is intentionally small:

- `TaskSpec`, `TaskConstraints`, and `TaskBudget` describe task input.
- `CommandResult` records real process facts only.
- `VerificationResult` wraps deterministic command-backed verification.
- `VerificationSpec` describes a deterministic verification command.
- `VerificationSummary` records ordered verification results and derived counts.
- `WorkspaceHandle` records a managed worktree's identity, branch, base ref, and
  resolved base commit.
- `WorkspaceChanges` records relative changed paths and a reviewable diff.
- `RunReport` records worker output, changed files, diff text, verification results, errors, and human-approval status.

Vendor-specific data belongs in explicit `extensions` dictionaries. Unknown top-level fields are rejected.

## Deferred decisions

The following are intentionally deferred until the single-worker CLI works:

- FastAPI service boundary
- Database choice
- React interface
- Queue or distributed worker
- OpenAI Agents SDK
- MCP server
- Automatic model selection
- Parallel task DAG
