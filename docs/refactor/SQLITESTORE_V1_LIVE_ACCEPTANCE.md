# SqliteStore V1 live acceptance

日期：2026-09-29。模型：`deepseek-v4.1-flash`，服务返回版本 `deepseek-v4-1-flash-260910`。

```text
Doctor Preference: FAIL
Longitudinal Memory: PASS
Store Failure Degradation: FAIL

SqliteStore V1 = NOT ACCEPTED
```

## 验收方式与服务状态

- 启动前未发现运行中的 Martin 后端，因此实际操作为加载新配置后重新启动服务；本机 8000 端口健康检查通过。
- 三个场景使用相同应用代码、真实 HTTP REST 路由、真实外部 LLM、真实 app.sqlite / SqliteStore / SqliteSaver，以及独立合成数据库。没有替换模型、工具返回或 Prompt。
- 验收进程单独监听本机 8001 端口，结束后关闭；正常服务继续运行。故障注入只作用于验收进程内的 Store.search，已撤销。
- 模型回调记录实际 SystemMessage 与用户输入、最终回答和不含 reasoning 的工具调用。Store 包装器记录真实返回值；snapshot 单独标注为候选投影，不能替代实际模型输入证据。
- 仅禁止验收进程的旧思维链日志，并将审计输出移入验收目录、去除 reasoning 字段；这些观测处理不改变业务返回或提示词。
- 运行产物保存在仓库外的 `validation/store-v1-live-20260929-104629/`：`evidence.json` 是结构化完整证据，`LIVE_ACCEPTANCE.md` 含三层证据与最终回答全文。不纳入 Git。

## A. Doctor Preference — FAIL

Thread A 输入：`以后报告请结论前置、200字以内、重点毛刺征。`

新建 Thread B，仅输入：`生成报告`。没有给 Thread B 重复偏好，也没有预写偏好记录。

| 证据层 | 实际结果 |
| --- | --- |
| Store retrieval | 真实模型调用 save_report_preference；`doctor/D001/preferences` 的 `report_style` 保存并被新 Thread 检索到：`conclusion_first=true`、`max_words=200`、`focus=["毛刺征"]`。通过。 |
| Prompt / Context injection | Thread B 的真实模型输入包含上述三项偏好。通过。 |
| Final LLM answer | 回答提及毛刺征未评估，但共 487 个字符，开头先说明报告服务失败，随后才给结论；不符合结论前置与 200 字以内。失败。 |

失败首先体现在 **LLM instruction following**，不能归因为偏好没存上或未注入。

**Prompt design** 存在需要处理的冲突：记忆投影统一声明“是数据，不是新的指令”，没有明确将已授权医生偏好提升为输出约束；主 Prompt 同时要求多个完整报告章节。当前一次 live 结果只能定位这些问题，尚不能证明某个 Prompt 改动足以修复。

同一场景还暴露报告工具问题：真实模型对缺失置信度传入 `score=null`；报告格式化/模板降级对空值进行数值格式化，记录 `unsupported format string passed to NoneType.__format__`，最终工具返回“报告生成失败”。Agent 随后自己整理了超长回复。返回的 CaseContext 仍出现“已生成病例报告。”，这是另一个需要修复的失败状态识别问题，本轮未修改它。

知识检索返回“知识库未初始化”。这是本次工具实际状态，不是 BGE 导入错误；本轮未更改或导入 RAG，也未将报告失败冒充成功。

## B. Patient Longitudinal Memory — PASS

合成历史：C001 / F001，2026-06-01，6mm；当前：C002 / F002，2026-09-01，8mm。两个观察均经真实授权服务写入 Store。新 Thread 绑定当前 C002，输入：`和上次相比，结节大小有什么变化？`

| 证据层 | 实际结果 |
| --- | --- |
| Store retrieval | `patient/P001/memory` 的真实 search 返回两条独立 Observation，历史 F001=6mm、当前 F002=8mm。通过。 |
| Prompt / Context injection | 实际模型输入的 CURRENT CASE FACTS 只有 F002=8mm；PATIENT HISTORICAL MEMORY 只有 F001=6mm。通过。 |
| Final LLM answer | 回答按两个日期分别列出 6.0mm、8.0mm，并明确“差值：+2.0mm”；没有把历史值当成当前值。结构化检查及语义复核通过。 |

回答原文节选：

> 1. 6.0mm（2026-06-01，右肺上叶，F001）
> 2. 8.0mm（2026-09-01，右肺上叶，F002，已确认）
>
> 差值：+2.0mm，两次检查间隔约 3 个月，按记录的直径计算增幅约 33%。

模型还说明需区分测量差异与真实生长，没有声称已经证实生长。这符合本场景的数据边界。

实现边界：当前 MemoryService 在 search 后依据业务库 confirmed Finding 重建 Store，snapshot 使用业务事实生成的观察投影。已证明真实 Store 读取、来源分区和最终回答链路；不应将此宣称为“脱离业务库、仅从 Store 恢复历史”的验收。

## C. Store Failure Degradation — FAIL

在独立新 Thread 的 Store.search 注入 OSError，输入：`和上次相比有没有变化`。

| 证据层 | 实际结果 |
| --- | --- |
| Store retrieval | 真实读取路径触发注入的 OSError；MemorySnapshot.available=false，当前 F002=8mm 保留。故障注入与降级快照通过。 |
| Prompt / Context injection | 候选投影含“历史记忆不可用；不得推断过去的检查结果或纵向变化”，但 API 在 Agent 创建之前返回 503，没有送到模型。失败。 |
| Final LLM answer | 模型调用次数为 0，没有 Final LLM answer。接口返回安全提示；不能算作真实模型降级通过。 |

接口原文：

> 当前病例可以继续分析，但历史记忆暂不可用，无法可靠比较本次与既往检查。请稍后重试或查看原始历史病例。

接口没有编造“无变化”或旧值；这是已有防护行为，未达到此次要求的“真实模型明确说明历史不可用”。

失败位置是 **Context injection / API 模型调用前的拦截**：`api/routers/agent.py` 中 REST 的历史比较守卫在创建 Agent 前返回，WebSocket 同类路径也直接发 error（本轮 live 只执行 REST，WebSocket 为代码检查及既有离线测试证据）。无法据此判断 C 的 LLM instruction following，因为模型根本没有执行。

## 阶段记录

### 已修改

- 新增验收脚本和脱敏证据（仓库外）；新增本报告并更新 V1 阶段入口与工作区进度。
- 未修改生产代码、Prompt、依赖、RAG 或既有未提交代码；未进入 V2。

### 已运行 / 已测试

- 新配置服务启动和健康检查通过；验收后正常服务健康、临时验收服务停止。
- 当前 V1 最小相关回归：`tests/memory`，11 passed，1 warning。
- 三个真实 LLM 验收场景全部尝试；A、B 实际调用模型，C 因真实 API 守卫没有调用模型。
- `git diff --check` 通过。

### 已通过

- B 的历史/当前值、+2mm、来源不混用。
- A 的保存、跨 Thread 检索与实际 Prompt 注入。
- C 的故障检测与接口拒绝编造（不等同完整场景通过）。

### 尚未通过 / 尚未验证

- A 的真实模型输出格式与长度；报告链空值兼容及失败状态识别。
- C 的不可用历史注入真实模型与最终降级回答。
- 本轮没有生产代码改动，没有重跑全量回归；此前 240 passed / 1 skipped 是离线基线，不能覆盖这次 live 失败。
- 修复仍应限定在 V1，重新验证 A/C 后再决定是否 ACCEPTED；本轮不扩大到 V2。
