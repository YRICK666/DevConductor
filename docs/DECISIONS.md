# Architectural Decisions

This file uses a lightweight ADR format.

---

## ADR-001: Local-first single-worker MVP

**Status:** Accepted  
**Date:** 2026-06-12

### Context

The long-term product will coordinate multiple coding agents, but parallel multi-agent behavior would hide basic reliability problems if introduced too early.

### Decision

Build a local CLI that runs one worker in an isolated Git worktree before adding parallelism, a web interface, or distributed infrastructure.

### Consequences

- The first milestone is small enough to test thoroughly.
- Core contracts can be validated against real repositories.
- Multi-agent orchestration is delayed until execution, verification, and cleanup are reliable.

---

## ADR-002: Shared instructions through AGENTS.md

**Status:** Accepted  
**Date:** 2026-06-12

### Context

Codex uses `AGENTS.md`, while Claude Code uses `CLAUDE.md`.

### Decision

Keep repository-wide rules in `AGENTS.md`. Keep `CLAUDE.md` as a thin compatibility file that imports `AGENTS.md`.

### Consequences

- Codex and Claude Code receive the same core rules.
- Instruction drift is reduced.
- Tool-specific guidance remains possible without duplicating the full document.

---

## ADR-003: Deterministic verification is independent of models

**Status:** Accepted  
**Date:** 2026-06-12

### Context

Coding agents can incorrectly report that tests passed or that a change is safe.

### Decision

Only process exit codes, parsed test artifacts, and rule-based checks determine verification status. Model reviews remain advisory.

### Consequences

- Results are auditable.
- A model cannot approve its own implementation.
- The orchestrator needs a controlled command runner and structured verification records.

---

## ADR-004: Pydantic 2 contracts for Stage 1 schemas

**Status:** Accepted
**Date:** 2026-06-12

### Context

Stage 1 needs structured task, command, verification, and run-report contracts before adding agent adapters or execution services.

### Decision

Use Python 3.12 and Pydantic 2 models for external and persisted contracts. Reject unknown top-level fields, keep vendor-specific fields under `extensions`, and use argument arrays for commands instead of shell strings.

### Consequences

- Invalid inputs fail before orchestration begins.
- Core schemas remain vendor-neutral.
- Later command runner and adapter implementations can depend on typed contracts without introducing their own parsing conventions.

