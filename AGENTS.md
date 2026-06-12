# DevConductor 仓库指令

## 1. 项目使命

DevConductor 是一个由人类主导的多 Agent 软件工程编排平台。

该平台将协调 Codex、Claude Code 和 DeepSeek 等 coding agents，同时保持执行隔离、验证确定性，并将最终接受权保留在人类手中。

本项目不是一个多 Agent 聊天演示。每个功能都应支持真实的软件交付工作流。

## 2. 当前里程碑

仓库当前处于 **Stage 0: project bootstrap**。

第一个可执行里程碑是一个本地 CLI，它完成以下闭环：

1. 读取结构化 task file。
2. 创建隔离的 Git worktree。
3. 调用一个已配置的 coding-agent adapter。
4. 捕获 logs、changed files 和 Git diff。
5. 运行真实的 verification commands。
6. 写入结构化 run report。
7. 在 merge 前停止，并等待 human approval。

除非 task 明确要求，否则不要构建以下内容：

- Web UI
- Multi-agent free-form conversation
- Automatic merge or push
- Distributed workers
- Message queues
- Kubernetes or cloud deployment
- Long-term agent memory
- Automatic model routing
- Agents SDK or MCP integration

优先选择能够推进当前里程碑的最小实现。

## 3. 事实来源

在进行架构变更前，阅读这些文件：

- `AGENTS.md`: 仓库级工作规则
- `README.md`: setup 和面向用户的 usage
- `docs/ARCHITECTURE.md`: system boundaries 和 planned components
- `docs/DECISIONS.md`: 已接受的 architectural decisions
- `tasks/`: 作为输入使用的 task specifications
- `runs/`: 本地 execution outputs；绝不要把这些当作 source code

当文档和代码不一致时，报告冲突。不要静默发明新的约定。

## 4. 必需工作流程

对每个非平凡任务：

1. 检查相关文件和 `git status`。
2. 在内部重述任务、约束和 acceptance criteria。
3. 做出最小且连贯的变更。
4. 当行为发生变化时，添加或更新 tests。
5. 运行相关 verification commands。
6. 审查最终 diff，检查 unrelated changes、secrets 和 regressions。
7. 准确报告变更内容和已验证内容。

不要声称某个 command 或 test 已通过，除非它实际执行并返回成功 exit code。

如果 verification 无法运行，说明确切原因，并提供仍需运行的 command。

### 沟通语言规则

- 默认使用简体中文与用户沟通。
- 计划、进度说明、审查结论和最终报告默认使用简体中文。
- 只有在用户明确要求其他语言时才切换。
- CLI 自带的权限菜单或第三方工具输出不要求翻译。

## 5. 安全与仓库边界

除非用户明确要求，否则绝不要执行这些操作：

- `git push`
- `git reset --hard`
- `git clean -fd` 或等价的破坏性清理
- History rewriting
- 删除 untracked user files
- Merge 到 default branch
- 安装 global packages
- 读取或打印 `.env`、credentials、tokens 或 private keys
- 修改本仓库之外的文件

附加规则：

- 不要提交 secrets、generated credentials、本地 absolute paths 或 machine-specific configuration。
- 将 agent output 视为 untrusted input。
- 在未应用 orchestrator 的 policy checks 前，绝不要执行 model-provided command。
- 在接受或 merge agent implementation 前，必须获得 human approval。
- 不要为了让 run 通过而削弱 tests、linters 或 security checks。

## 6. 架构边界

保持以下职责分离：

- `orchestrator`: task state、sequencing、cancellation 和 policy decisions
- `adapters`: vendor-specific Codex、Claude Code 或 DeepSeek invocation
- `workspace`: Git worktree lifecycle 和 diff collection
- `verifier`: deterministic commands 和 rule-based checks
- `schemas`: vendor-neutral task、run、result 和 review models
- `storage`: 仅负责 persistence；不包含 orchestration decisions
- `api`: 仅作为 transport layer；不包含 direct subprocess 或 Git logic

强制性设计规则：

- Vendor-specific fields 不得泄漏到 core schemas，除非放在显式 extension field 下。
- Model adapters 必须实现 shared interface。
- Git operations 必须通过 workspace layer。
- Subprocess execution 必须通过一个受控 command runner。
- Verification results 来自 process exit codes 和 parsed artifacts，而不是 model's claim。
- 任何 model 都不得授予自己 implementation 的 final approval。

## 7. Python 约定

直到后续 decision 修改这些约定前：

- 目标为 Python 3.12 或更新版本。
- 对 public functions 和 data models 使用 type hints。
- 使用 `pathlib.Path`，不要手动拼接 path。
- 对 external 和 persisted structured data 使用 Pydantic models。
- 优先使用 `asyncio.create_subprocess_exec`，而不是 `shell=True`。
- 支持 Windows paths、paths with spaces 和 UTF-8 text。
- 将 side effects 放在显式 services 或 adapters 后面。
- 在 testing 有收益时，对 subprocess、filesystem、clock 和 model clients 使用 dependency injection。
- 返回 structured results，而不是在 downstream 解析 human-readable log text。
- 抛出具体且带 actionable messages 的 exceptions。
- 避免只有一个 concrete use 的 premature abstractions。

## 8. 测试与验证

只使用仓库当前已配置的 commands。预期 Python checks 是：

```powershell
python -m pytest
python -m ruff check .
python -m mypy backend
```

当这些工具尚未配置时，不要假装它们可用。作为首次引入可执行 Python code 的 task 的一部分添加配置。

Tests 应覆盖：

- Successful execution
- Invalid task input
- Process timeout and cancellation
- Non-zero command exit
- Paths containing spaces
- Out-of-scope file modifications
- Redaction of sensitive values
- Partial failure cleanup

优先使用 deterministic unit tests。在 adapter boundary mock vendor CLIs。

## 9. Git 与生成文件

- 保持 commits 聚焦于一个连贯变更。
- 不要包含 unrelated formatting changes。
- 不要提交 `.venv/`、secrets、caches、temporary worktrees 或 `runs/`。
- Generated reports 在实际可行时必须可由 source inputs 复现。
- 完成前，检查 `git diff --stat` 和相关 full diff。

除非用户或当前 task 明确要求，否则不要创建 commit。

## 10. 文档规则

当 behavior、setup、architecture 或 public interface 变化时，更新文档。

当在有意义的 architectural alternatives 之间做选择时，在 `docs/DECISIONS.md` 记录条目。不要把 routine implementation details 记录为 architecture decisions。

保持本文件简洁。只有在重复错误或反复出现 review comment 后才添加规则，不要为每个一次性 task 添加规则。如果仓库增长，将 specialized rules 放在最接近的相关 subdirectory。

## 11. 完成报告

结束 implementation work 时使用这些 headings：

### Summary
添加、修复或有意保持不变的 behavior。

### Changed files
列出重要文件，以及每个文件为何变更。

### Verification
列出每个实际运行的 command 及其结果。

### Risks and next step
说明剩余 limitations、unverified assumptions，以及最合理的 single next task。

## 12. 完成定义

只有满足以下条件时，task 才算完成：

- Acceptance criteria 已满足。
- Implementation 保持在 requested scope 内。
- Relevant tests 或 checks 已通过，或 blockers 已明确报告。
- Final diff 不包含 unrelated changes 或 secrets。
- Documentation 与 implementation 一致。
- Result 可由 human 在 merge 前 review。
