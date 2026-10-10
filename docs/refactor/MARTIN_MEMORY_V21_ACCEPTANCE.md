# Martin 长期记忆 V2.1 可信治理验收

日期：2026-10-09。结论：**ACCEPTED，限本报告所列范围**。

基线为 `main@b8fd8b3`，实施分支 `codex/memory-v21-governance`。实现对照 [V2 实施计划](../plans/MARTIN_MEMORY_V2_IMPLEMENTATION_PLAN.md)；Batch 0–3 已完成。V2.2 / V2.3 尚未实施。本报告是软件行为验收，不是临床安全认证。

## 1. 已实现能力

| 能力 | 行为与主要入口 |
| --- | --- |
| 可解释来源 | `models.py` / `lifecycle.py` 区分 `message`、`api_submission`、`business_event`、`legacy_unknown`。Agent 写入绑定本轮真实 HumanMessage；API 保存认证医生及提交 ID，不虚构消息 ID。旧记录按读取适配，不批量改写原库。 |
| 偏好版本 | `service.py` 为新偏好分配独立 ID，保存替代链；保持 V1 `report_style` 返回形状。旧版投影受 typed 历史治理，撤回或损坏的记录不会恢复旧偏好。 |
| 生命周期 | 普通召回排除已替代、撤回、失效或过期记录；历史查询保留受权条目。按精确 memory ID 修订/撤回，保存操作者、时间、原因与来源；重复修订可返回同一继任版本。 |
| 声明与事实 | 新增 `clinical_claim`；医生陈述及 Finding 纠正标记为未核实，`business_fact_updated=false`。明确目标的纠正与当前业务值做只读冲突检查，记忆写入不修改 Finding。 |
| 全路径门禁 | `governance.py` / Router / Service 对 typed、语义回源、旧版偏好、私人笔记和病例记忆重新授权并检查来源、状态和时效；业务确认事实继续从 SQL 获取。 |
| 当前轮刷新 | 成功的记忆变更工具执行后，Agent 在下一次模型调用前重新获取记忆与偏好；撤回失败不能宣称成功。历史聊天中的旧要求只作为历史。 |
| 输出规则 | 当前医生明确要求优先于长期展示偏好；支持本次不限字数、保存不设上限及“本轮明确为复杂病例时不限字数”。不把一次性覆盖自动写为长期规则。 |
| 管理界面 | 病例工作台“长期记忆”抽屉：来源、状态、修订/撤回、历史、未核实声明和条件报告偏好。切换会话或关闭后丢弃旧异步结果。 |
| 日志隐私 | Agent 工具日志保留名称、状态与聚合信息；审计不持久化原始参数、用户全文、最终回答正文或完整思维链。Store、Agent API 与执行层异常日志仅记录异常类型，避免原文和 traceback 带入请求片段。生命周期原因属于受权记忆历史，不写入运行日志。 |

业务库、会话 checkpoint、长期记忆源库和语义索引仍各自承担原职责；医学知识库未混入患者记忆。

## 2. 离线回归

本批初始相关基线：164 passed。最终相关回归：**340 passed / 0 failed / 0 skipped，61.22 秒**；出现两项依赖弃用警告（Starlette TestClient/httpx、langchain-community），不属于测试失败。此结果包含收尾日志脱敏修复及四项隐私回归。

使用已选定且符合项目要求的 Python 3.10.19，经正式包装器运行；以下命令不包含本机解释器路径：

```powershell
# 先将 MARTIN_TEST_PYTHON 设置为已选定的项目解释器。
.\scripts\run_tests.ps1 tests/memory tests/access tests/auth tests/business tests/entity `
  tests/test_agent_pipeline.py tests/test_agent_state_regressions.py tests/test_agent_tools.py `
  tests/test_case_context.py tests/test_session_persistence.py tests/test_sessions.py `
  tests/test_web_api.py tests/test_phase1_integration.py tests/test_report_finding_input.py `
  tests/test_report_finding_format.py tests/test_report_missing_measurements.py `
  tests/test_runtime_output.py tests/test_cli_commands.py tests/test_cli_ui.py `
  --basetemp=tmp/pytest-v21-final-20261009-3 -q
```

范围包含计划 A–L、V1/V1.1 偏好与 Finding 回填、授权、SQLite 重开、Agent、REST、WebSocket、会话恢复、报告及 CLI。主要新增回归在 `tests/memory/test_memory_governance.py`、`test_memory_governance_core_review.py` 和 Agent 状态测试。

具体保护包括：真实消息来源；API 提交不冒充消息；助手来源拒绝；裸 V1 偏好撤回后不复活；损坏来源/逻辑 key 不回退为有效偏好；仅置信度变化也生成修订；重试仍验证来源和原因；布尔值不强制转换成 Finding 测量值；撤回后 Prompt 更新；过期、旧向量、越权与故障过滤。`test_memory_privacy_logs.py` 及 Agent 状态测试另覆盖 Store/WS 降级异常、自由文本查询和病例备注日志的合成隐私标记不泄漏。

真实 SQLite 回滚测试使用触发器，在第一条删除语句已经执行后中止后续插入，随后关闭并重开源库，验证当前投影与记录状态均恢复。该测试区别于“写入前直接抛异常”的模拟。

## 3. 前端构建与浏览器验收

`frontend` 中执行 `npm run build`，TypeScript 检查及 Vite 生产构建通过（1782 个模块）。构建仍有依赖注释和大 chunk 提示；不影响本次构建结果。生成的 dist 与 tsbuildinfo 不作为本批源码改动交付。

浏览器使用独立合成医生、病例及四个 SQLite 文件，未操作正式患者库。实际验证：

- 从会话进入病例工作台并打开“长期记忆”；来源显示“医生直接提交”、认证医生、提交 ID 及未核实标签。
- 精确修订一条声明；旧版显示已替代，新版显示有效；历史可见操作者与原因。
- 撤回新版；默认列表不再显示该条；打开包含无效记录的选项后显示已撤回，并可查撤回历史。
- 保存不设字数上限及复杂病例条件偏好；成功提示、有效偏好与提交来源同步显示。

本机截图 `tmp/v21-memory-management-20261009.jpg` 仅含合成数据，不入 Git。移动端专门适配、真实影像上传与完整业务发现流程未纳入此轮浏览器验收。

## 4. 真实模型验收与公开回答复核

脚本：`validation_scripts/memory_governance_live_acceptance.py`。模型：用户确认的火山方舟 `deepseek-v4.1-flash`；使用用户指定的兼容服务地址。凭据只从本机环境/未入库 `.env` 读取。

运行命令：

```powershell
& $env:MARTIN_TEST_PYTHON validation_scripts/memory_governance_live_acceptance.py
```

本次使用独立 app/store/checkpoint/vector/空知识库文件、真实 REST/WS 与本地 BGE；**26 次真实模型调用，15 条公开回答，八类场景共 37 项结构化检查全部通过**。模型调用数包含工具步骤，不能等同独立验收场景数。

| 场景 | 自动检查 | 公开回答语义复核 |
| --- | --- | --- |
| A 偏好、当轮覆盖、版本替代 | 9/9 | 跨会话结论前置且小于 200 字；当前不限字数、所见先于结论生效；新修订已注入，不把本轮要求再次存为永久规则。 |
| B 撤回、REST/WS、旧会话恢复 | 3/3 | 三条回答均使用当前确认 8 mm；不宣布旧偏好仍有效，源偏好为空而历史保留。 |
| C 未核实过敏声明 | 4/4 | 明确“尚未核实”，业务库没有确认过敏记录，不能推断过敏不存在，也未声称已更新业务库。 |
| D Finding 纠正冲突 | 4/4 | 同时呈现确认 8 mm、医生提议 9 mm 与待复核状态，确认值仍为 8 mm。 |
| E 已撤回向量残留 | 5/5 | 原生向量确有残留命中，回源拒绝；Prompt 与公开回答无撤回原文，明确没有可追溯的历史决策原因。 |
| F Store/向量故障 | 5/5 | Store 不可用时仅保留当前 8 mm，不编造 6 mm 或“无变化”；向量故障明确说明，Exact/Temporal 事实仍可用。 |
| G 医生/患者隔离与撤销授权 | 4/4 | 不推断不可见的私人讨论；另一医生只可见获授权的共享业务事实；他人历史与撤销授权请求被拒绝。 |
| H 历史时间与病灶身份 | 3/3 | 正确保留 2024 年 6 mm 和 2026 年 8 mm，数值差 2 mm；明确无法证明同一病灶，不计算生长率。 |

脚本将自动通过后的场景标为 `REVIEW`，防止字符串断言冒充完整语义判断。本报告及同目录 `semantic_review.json` 记录了对全部公开回答的复核；原始 evidence 保留，不覆盖原检查结果。

证据目录：`tmp/validation/store-v1-live-20261009-171941-189555/`，包含 `evidence.json`、隔离清单与语义复核。服务已停止，未产生 harness_error。验收公开回答、Prompt 和合成运行库不入 Git。

## 5. 限制与后续阶段

1. **SQLite 事务适配依赖安装版本**：当前 SqliteStore 公共 batch 的游标在异常退出时仍提交。生命周期批写在同连接锁下明确 BEGIN/COMMIT/ROLLBACK，并复用其私有 SQL 构建方法 `_batch_put_ops`。真实中途失败测试已验证；升级此依赖时须重跑并核验私有接口，不能默认兼容。
2. **并发范围**：进程内 RLock 不提供跨 worker 修订冲突保障。多进程竞争、锁等待、性能阈值和部署门禁留给 V2.3；本报告不承诺多 worker 安全。
3. **增长范围**：完整全局 token 预算、近重复去重和带来源摘要留给 V2.2。当前保留有限分区的完整 JSON 条目，避免截断来源，但不宣称已实现统一 token 预算。
4. **病灶身份**：尚无稳定跨检查 lesion ID。真实回答会声明身份未确认，但一次隔离回答曾在数值列表中使用“较前增大 2 mm”，随后明确不可断定同一病灶增大。复核仅接受其整体限定语义，不能将一次验收推广为所有模型措辞都无歧义；后续应评估更严格的数值差表达。
5. **业务确认**：未核实过敏或 Finding 提议不会自动成为业务事实；新增正式临床确认工作流需另行设计。撤回记忆也不是删除业务 Finding。
6. **未覆盖范围**：未重跑完整 CT/MONAI 真推理、真实医学语料 RAG、所有报告结构完整性和生产临床数据验收。本次报告中的测试数字仅代表所列相关测试集。
7. **数据与 Git**：采用读取适配及新记录版本化，未迁移或重写正式运行库。代码仍在实施分支，未提交或推送；原有用户文件与运行数据保留。

交付静态检查：本批新增 Python 文件按 Black / isort 格式化，既有文件仅格式化变更区间及导入；`git diff --check` 通过。所列源码与交付文档的凭据字面量检查无命中，`.env`、本机笔记、验收证据、截图和临时工具均已排除入库。

下一阶段按已批准计划进入 V2.2：先建立统一预算与省略理由，再处理近重复和带源指针的摘要，并验证源撤回使摘要失效。V2.3 在测得质量与并发基线后定义阈值。
