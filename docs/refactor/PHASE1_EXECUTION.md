# Phase 0 / Phase 1 执行规则

## 范围

Phase 0 恢复可追踪源码、兼容环境与 baseline；Phase 1 只修单请求状态正确性、工具结果解析和可信持久化。验收通过前不进入业务数据库、登录、Patient/Case/Thread、权限、长期记忆、ContextBuilder、摘要或压缩。
本阶段不扩展 report_draft，不处理并发写、多worker、case_version、outbox、复杂事务或失败补偿。

## 执行顺序

1. 检查正式工作树与备份，保留已有 Phase 1 修改；恢复动作不得重复覆盖已完成工作。
2. 按正式项目配置明确解释器、依赖和可用服务，记录版本，不继承旧机器盘符。
3. 在相同环境评估原基线与修改后代码；保存基线时不 reset 当前工作树。
4. 记录 Python、环境、依赖、后端启动、前端启动、已有测试、SQLite、LLM、MONAI 状态。
5. 运行最小单测，再做真实 LangGraph/SqliteSaver 与 API 测试；修复失败后重新运行受影响范围。
6. 验收全部满足后审查敏感数据及 diff，再提交 `fix: stabilize agent state and tool result handling`。

## F01：CaseContext 状态协议

工具更新不能被旧 Graph 输入快照覆盖。同轮下一次模型调用必须看到新值；成功完成调用后持久化，重新创建 AgentExecutor 并使用同 thread 必须恢复新值。最终保存正确和同轮推理正确分别验证，不预设当前草稿实现已经正确。

## F02：当前轮工具解析

本轮边界为最后一条 HumanMessage 后的消息。调用和结果严格按 tool_call_id 配对，不能按返回顺序配对。历史调用不能重复出现在本轮 intermediate_steps 或重复进入审计。

## F03：持久化失败

save_case_context、checkpoint 或 SQLite 写入失败必须产生受控失败；REST 不返回正常成功，WebSocket 不发送成功 final，前端不得显示保存成功。模型生成回答不代表保存成功。

## 测试矩阵

| 类型 | 验证 | 必要断言 |
|---|---|---|
| 单元A | update_case_context | 初始年龄空，真实工具调用后为62；测试使用实际工具参数 user_input |
| 单元B | 旧 Graph 快照 | 快照年龄空、工具对象62，结果仍62 |
| 单元C | 乱序结果 | A/B调用，B/A结果，各自对应正确 |
| 单元D | 历史过滤 | 上轮A本轮B，仅返回B；无工具新轮不重复历史 |
| 单元E | 保存失败 | CasePersistenceError或等价受控错误，不返回成功 |
| 集成A | 真实SQLite恢复 | 真实LangGraph+SqliteSaver，完成invoke，关闭存储并重新创建后同thread年龄62 |
| 集成B | 同轮Prompt | 工具更新后截获实际下一次模型输入，包含62；不只调用Prompt辅助函数 |
| 集成C | CT状态 | analyze_image写入nodules，真实保存重开仍存在；可模拟检测器，但明确未验证真实MONAI |
| 集成D | REST/WebSocket | 注入checkpoint失败，REST非成功、WS error且无成功final |
| 回归 | 原有流程 | 基础聊天、会话隔离、新会话、历史恢复、工具失败与原CT流程无明显回归 |

## 验收

- [ ] Git工作区可安全追踪，原修改有备份。
- [ ] Python与依赖明确，项目基本启动。
- [ ] 单元A–E通过。
- [ ] 真实SQLite重启恢复通过。
- [ ] 实际同轮模型输入可见工具更新。
- [ ] analyze_image状态保存恢复通过。
- [ ] REST与WebSocket持久化失败不会返回成功。
- [ ] 原基础聊天与CT流程无明显回归。

任何关键项未通过，Phase 1 都未完成。资源缺失记为未验证或Skipped，不得勾选通过。

## 当前执行记录的去向

主要命令、结果、问题、阻塞和下一步写入已有工作区 REFACTOR_PROGRESS.md；总体路线参照 MEDICAL_AI_AGENT_REFACTOR_PLAN.md，避免复制出两套独立进度。
当前实际进展以执行记录为准。

