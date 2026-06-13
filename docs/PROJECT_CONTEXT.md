# DevConductor 项目上下文

## 项目目标

DevConductor 是一个人类主导的多 Agent 软件工程编排平台。

系统负责隔离执行、确定性验证、运行记录和结果审查；人类保留最终接受、拒绝与合并权。

## 当前已经完成

- Stage 0：仓库初始化与 `AGENTS.md`
- Stage 1：`TaskSpec`、`CommandResult`、`RunReport` 等核心 Schema
- Stage 2：异步 `CommandRunner`
- Stage 3：确定性 `Verifier`
- Stage 4：Git worktree `WorkspaceManager`
- Stage 5：`AgentAdapter` 与 `CodexAdapter`
- Stage 6：`SingleWorkerCoordinator` 与本地 CLI

## 当前运行闭环

`TaskSpec`
→ `WorkspaceManager`
→ `AgentAdapter`
→ `WorkspaceChanges`
→ `Verifier`
→ `RunReport`
→ `awaiting_approval`

## 核心边界

- 所有进程通过 `CommandRunner`。
- 所有 Git 工作区操作通过 `WorkspaceManager`。
- `Verifier` 只相信真实退出码和结构化结果。
- `Adapter` 不负责验证、审批或合并。
- Agent 不得批准自己的实现。
- 不自动 `commit`、`merge` 或 `push`。
- 人类最终决定是否接受。

## 下一阶段

Stage 7：结构化 `RunEvent` 事件流。

预期事件包括：

- `run.started`
- `workspace.created`
- `agent.started`
- `agent.output`
- `agent.completed`
- `verification.started`
- `verification.completed`
- `run.awaiting_approval`
- `run.failed`
- `run.cancelled`

`RunEvent` 将为后续 Web API、SSE/WebSocket 和可视化控制台提供数据基础。

## 模型使用策略

- 不需要模型：Git、测试、Lint、类型检查、安全扫描。
- Codex profile `mini`：默认 profile，用于文档、扫描、简单测试、小范围代码修改。
- Codex profile `standard`：用于中等复杂度实现和常规修复。
- Codex profile `strong`：用于架构、跨模块实现、复杂问题和最终审查。
- 新任务默认使用 `mini`，不得静默继承全局 Codex 模型配置。
- `max_cost_usd` 当前是 advisory cost target；在没有可信 billing data 前不视为强制执行的预算。
- 轻量模型失败后可由人类选择升级；当前不实现自动 strong-model escalation。

## 标准本地命令

- `.\scripts\project-status.ps1`
- `.\scripts\verify.ps1`
- `.\scripts\start-stage.ps1`
- `.\scripts\new-codex-task.ps1`
- `.\scripts\finish-stage.ps1`
