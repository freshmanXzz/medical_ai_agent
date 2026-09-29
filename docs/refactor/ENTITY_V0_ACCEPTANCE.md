# Entity V0 验收记录

日期：2026-09-29。阶段状态：已验收，允许进入 SqliteStore V1。

## 已修改

- Batch 1–5 已落地业务实体、服务端会话、授权、临床事实与纵向 Finding；Batch 6 落地 Thread 与 SQLite checkpoint 的删除联动。
- 修复旧 `tests/test_one_click.py` 中两个脚本步骤被 pytest 当成独立测试后缺少 `result` fixture 的问题；命令行一键流程保留，pytest 使用合成输入与本地模拟链，不调用外部 LLM。
- RAG 原定 small 模型已安装在 Git 忽略的 `models/embedding/bge-small-zh-v1.5`；生产向量库未改动。

## 已运行 / 已测试 / 已通过

- Entity V0 专项：52 passed。覆盖实体坐标、医生授权、6mm 与 8mm 两条 Finding 并存、真实 SqliteSaver checkpoint 删除，以及删除失败时保留业务 Thread。
- Phase 1 核心与 Web/阅片回归：56 passed。
- BGE 恢复后、修复旧测试前的全量结果：227 passed、1 skipped、2 errors；仅两处旧 `result` fixture 错误，日志：`D:/agent_martin/validation/entity-v0-full-after-bge-clean-env-20260929.log`。
- 两处测试单独重跑：2 passed。
- 最终全量回归：**229 passed、1 skipped、0 failed、0 errors**，日志：`D:/agent_martin/validation/entity-v0-full-final-20260929.log`。
- `git check-ignore -v` 确认模型文件命中 `.gitignore` 的 `models/` 规则；模型文件不进入 Git。

## 尚未验证

- 真实 LLM 请求、真实 MONAI 权重与影像推理不属于本轮核心回归，不能据模拟/跳过测试宣称通过。全量测试仍有 1 项跳过与旧测试告警。

## 阶段决定

Entity V0 执行计划第 9–10 节的全量回归门槛已满足。正式结束 Entity V0 验收，下一阶段为 SqliteStore V1。Store 仍须遵守 `ADR-001-entity-store-boundary.md`：业务事实与授权由 app.sqlite 管理，跨 Thread 记忆由 Store 管理，Thread 状态由 Saver 管理。
