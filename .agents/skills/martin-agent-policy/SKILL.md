---
name: martin-agent-policy
description: 维护 Martin Agent、系统提示词、工具路由、CaseContext、会话持久化、来源边界或审计日志时使用；适用于修改 martin/agent、Agent API 或相关测试的任务。
---

# Martin Agent Policy

## 工作流

1. 先阅读 `martin/agent/agent.py`、`tools.py`、`prompt.py`、`case_context.py` 与 `sessions.py`；涉及 API 时同时读取 `api/routers/agent.py`。
2. 把行为改动落实到工具描述、Prompt、状态保存和测试，不只修改其中一处。
3. 运行与修改范围相符的测试；涉及会话或上下文时覆盖新会话、恢复历史会话和工具失败路径。

## 不可破坏的契约

- `thread_id` 是会话隔离边界；`CaseContext` 必须随 checkpoint 恢复，不能串到其他会话。
- Prompt 中登记的工具、触发条件和实际注册工具必须一致；新增或移除工具时同步更新测试和文档。
- 来源、指南、阈值或证据类回答必须经 `retrieve_knowledge` 支持。不能把模型常识说成本次检索结果。
- 不记录完整思维链、未脱敏用户原文或不必要的工具参数到审计/运行日志；保留最小结构化依据。
- 保持 CLI、REST 和 WebSocket 使用同一 Agent 行为，除非任务明确要求分叉。

## 验证

使用 `AGENTS.md` 规定的 Python 环境或测试包装器。优先运行相关的 Agent、工具、会话和 API 测试；完整约束见 `AGENTS.md` 与 `docs/ARCHITECTURE.md`。
