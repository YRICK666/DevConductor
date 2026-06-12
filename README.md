# AgentForge

AgentForge is a human-led multi-agent software engineering orchestration platform.

Its goal is to coordinate coding agents such as Codex, Claude Code, and DeepSeek in isolated workspaces, verify their work with deterministic tools, and require human approval before code is accepted.

## Current status

Stage 0: repository bootstrap and engineering rules.

The first executable milestone will be a local single-worker CLI:

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
backend/app/       Python application code
backend/tests/     Python tests
docs/              Architecture and decision records
frontend/          Reserved for a later web interface
tasks/             Versioned example task specifications
runs/              Local generated run artifacts; ignored by Git
```

## Agent instructions

- Codex reads `AGENTS.md`.
- Claude Code reads `CLAUDE.md`, which imports `AGENTS.md`.
- Repository rules should be maintained primarily in `AGENTS.md`.

## Next milestone

Define the Stage 1 contracts:

1. `TaskSpec`
2. `AgentAdapter`
3. `CommandRunner`
4. `WorktreeManager`
5. `RunReport`
