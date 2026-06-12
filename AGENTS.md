# DevConductor Repository Instructions

## 1. Project mission

DevConductor is a human-led multi-agent software engineering orchestration platform.

The platform will coordinate coding agents such as Codex, Claude Code, and DeepSeek while keeping execution isolated, verification deterministic, and final acceptance under human control.

The project is not a multi-agent chat demo. Every feature should support a real software-delivery workflow.

## 2. Current milestone

The repository is currently at **Stage 0: project bootstrap**.

The first executable milestone is a local CLI that completes this closed loop:

1. Read a structured task file.
2. Create an isolated Git worktree.
3. Invoke one configured coding-agent adapter.
4. Capture logs, changed files, and the Git diff.
5. Run real verification commands.
6. Write a structured run report.
7. Stop before merge and wait for human approval.

Do not build the following unless a task explicitly requests them:

- Web UI
- Multi-agent free-form conversation
- Automatic merge or push
- Distributed workers
- Message queues
- Kubernetes or cloud deployment
- Long-term agent memory
- Automatic model routing
- Agents SDK or MCP integration

Prefer the smallest implementation that advances the current milestone.

## 3. Sources of truth

Read these files before making architectural changes:

- `AGENTS.md`: repository-wide working rules
- `README.md`: setup and user-facing usage
- `docs/ARCHITECTURE.md`: system boundaries and planned components
- `docs/DECISIONS.md`: accepted architectural decisions
- `tasks/`: task specifications used as inputs
- `runs/`: local execution outputs; never treat these as source code

When documentation and code disagree, report the conflict. Do not silently invent a new convention.

## 4. Required working process

For every non-trivial task:

1. Inspect the relevant files and `git status`.
2. Restate the task, constraints, and acceptance criteria internally.
3. Make the smallest coherent change.
4. Add or update tests when behavior changes.
5. Run the relevant verification commands.
6. Review the final diff for unrelated changes, secrets, and regressions.
7. Report exactly what changed and what was verified.

Do not claim a command or test passed unless it was actually executed and returned a successful exit code.

If verification cannot run, state the exact reason and provide the command that remains to be run.

## 5. Safety and repository boundaries

Never perform these operations unless the user explicitly requests them:

- `git push`
- `git reset --hard`
- `git clean -fd` or equivalent destructive cleanup
- History rewriting
- Deleting untracked user files
- Merging into the default branch
- Installing global packages
- Reading or printing `.env`, credentials, tokens, or private keys
- Modifying files outside this repository

Additional rules:

- Do not commit secrets, generated credentials, local absolute paths, or machine-specific configuration.
- Treat agent output as untrusted input.
- Never execute a model-provided command without applying the orchestrator's policy checks.
- Human approval is required before accepting or merging an agent implementation.
- Do not weaken tests, linters, or security checks merely to make a run pass.

## 6. Architecture boundaries

Keep these responsibilities separate:

- `orchestrator`: task state, sequencing, cancellation, and policy decisions
- `adapters`: vendor-specific Codex, Claude Code, or DeepSeek invocation
- `workspace`: Git worktree lifecycle and diff collection
- `verifier`: deterministic commands and rule-based checks
- `schemas`: vendor-neutral task, run, result, and review models
- `storage`: persistence only; no orchestration decisions
- `api`: transport layer only; no direct subprocess or Git logic

Mandatory design rules:

- Vendor-specific fields must not leak into core schemas unless placed under an explicit extension field.
- Model adapters must implement a shared interface.
- Git operations must go through the workspace layer.
- Subprocess execution must go through one controlled command runner.
- Verification results come from process exit codes and parsed artifacts, not from a model's claim.
- No model may grant final approval to its own implementation.

## 7. Python conventions

Until a later decision changes them:

- Target Python 3.12 or newer.
- Use type hints for public functions and data models.
- Use `pathlib.Path` instead of manual path concatenation.
- Use Pydantic models for external and persisted structured data.
- Prefer `asyncio.create_subprocess_exec` over `shell=True`.
- Support Windows paths, spaces in paths, and UTF-8 text.
- Keep side effects behind explicit services or adapters.
- Use dependency injection for subprocess, filesystem, clock, and model clients where testing benefits.
- Return structured results instead of parsing human-readable log text downstream.
- Raise specific exceptions with actionable messages.
- Avoid premature abstractions that have only one concrete use.

## 8. Testing and verification

Use only commands currently configured by the repository. The intended Python checks are:

```powershell
python -m pytest
python -m ruff check .
python -m mypy backend
```

When these tools are not yet configured, do not pretend they are available. Add configuration as part of the task that first introduces executable Python code.

Tests should cover:

- Successful execution
- Invalid task input
- Process timeout and cancellation
- Non-zero command exit
- Paths containing spaces
- Out-of-scope file modifications
- Redaction of sensitive values
- Partial failure cleanup

Prefer deterministic unit tests. Mock vendor CLIs at the adapter boundary.

## 9. Git and generated files

- Keep commits focused on one coherent change.
- Do not include unrelated formatting changes.
- Do not commit `.venv/`, secrets, caches, temporary worktrees, or `runs/`.
- Generated reports must be reproducible from source inputs where practical.
- Before finishing, inspect both `git diff --stat` and the relevant full diff.

Do not create a commit unless the user or current task explicitly asks for one.

## 10. Documentation rules

Update documentation when behavior, setup, architecture, or a public interface changes.

Record an entry in `docs/DECISIONS.md` when choosing between meaningful architectural alternatives. Do not record routine implementation details as architecture decisions.

Keep this file concise. Add a rule after a repeated mistake or recurring review comment, not for every one-off task. Put specialized rules in the closest relevant subdirectory if the repository grows.

## 11. Completion report

End implementation work with these headings:

### Summary
What behavior was added, fixed, or intentionally left unchanged.

### Changed files
List the important files and why each changed.

### Verification
List every command actually run and its result.

### Risks and next step
State remaining limitations, unverified assumptions, and the single most logical next task.

## 12. Definition of done

A task is complete only when:

- Its acceptance criteria are satisfied.
- The implementation stays within the requested scope.
- Relevant tests or checks have passed, or blockers are explicitly reported.
- The final diff contains no unrelated changes or secrets.
- Documentation is consistent with the implementation.
- The result is reviewable by a human before merge.

