---
name: martin-web-workstation
description: 维护 Martin Vue 临床工作站、Pinia 状态、FastAPI REST 或 WebSocket、病例恢复、Copilot、上传或报告入口时使用；适用于 frontend、api 和端到端交互修改。
---

# Martin Web Workstation

## 工作流

1. 先确认修改属于前端展示、Pinia 状态、REST API、WebSocket 协议或其组合；读取对应请求/响应模型。
2. 保持工作站以病例和影像分析为中心；Copilot 是可收起的辅助面板，不应重新挤占主工作区。
3. 修改状态字段时检查新病例、恢复病例、上传中、失败、无结节和知识为空状态。

## 不可破坏的契约

- WebSocket 是优先通道，失败时 REST 回退必须仍能发送消息、更新 `CaseContext` 与完成状态。
- 恢复历史病例必须恢复会话消息、病例上下文和由结节重建的报告输入，不要求用户重复检测。
- 后端 API、Pydantic 模型、`caseStore` 和 `chatStore` 的字段变更必须同步；不以仅修改视觉组件代替数据兼容性检查。
- 桌面端 Copilot 不挤压分析区；窄屏必须无重叠、可键盘访问且长文件名/消息不溢出。

## 验证

前端执行 `npm run build`；后端或协议修改运行相关 API 测试。手动覆盖上传、对话、WebSocket 回退、历史恢复和报告入口，参考 `README.md` 的 Web 工作流。
