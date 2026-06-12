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

Creates and removes isolated Git worktrees, records the base revision, and collects changed files and diffs.

### Command runner

Runs approved commands with timeout, cancellation, output capture, and secret redaction.

### Verifier

Runs deterministic tests and policy checks. A model's statement that tests passed is never accepted as proof.

### Schemas

Define task input, agent execution request, command result, verification result, and final run report.

The current implemented schema slice is intentionally small:

- `TaskSpec`, `TaskConstraints`, and `TaskBudget` describe task input.
- `CommandResult` records real process facts only.
- `VerificationResult` wraps deterministic command-backed verification.
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

