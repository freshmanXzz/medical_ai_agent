# MARTIN_PRE_REFACTOR_VALIDATION_HANDOFF.md

> 致：Entity V0 决策 / 实施 Agent
> 来自：Independent Validation Agent（2026-09-28 16:30）
> 性质：Pre-Refactor 基线验证结果转达。本轮为只读验证：未改生产代码、未建 app.sqlite、未提交 Git、未调用真实外部 LLM。

---

## 一句话结论

**GO Entity V0** —— 按 `D:/agent_martin/MARTIN_ENTITY_V0_EXECUTION_PLAN.md` 从 Batch 1 开工。

---

## 已核实事实

完整报告：`D:/agent_martin/validation/pre-refactor/PRE_REFACTOR_VALIDATION_REPORT.md`（附 8 份证据日志，同目录）。

| 项 | 结果 | 证据文件 |
|---|---|---|
| Phase 1 Core（F01/F02/F03 + tool_call_id 配对 + 乱序结果 + persistence failure） | **35 passed / 0 failed** | phase1-core.log |
| 全量回归（跑满 178 项，未用 -x 提前停） | 170 passed / 1 failed / 5 errors / 2 skipped，880s | full-suite.log |
| 未通过 6 项归因 | 全部同一根因：`BAAI/bge-small-zh-v1.5` 从 huggingface.co 下载 config.json ReadTimeout，本地缓存无副本 → **DEFERRED_ENVIRONMENT** | rag-deferred.log |
| Entity Gap（8 问） | doctor_id / patient_id / case_id / auth / access 代码 **0 匹配**；app.sqlite **不存在**；memories 表无 | entity-gap-check.md |
| SqliteSaver | data/sessions.sqlite 仅 checkpoints/writes 两表；thread_id 仍由请求传入（默认 "default"），是唯一稳定身份键 | sqlite-saver-check.log |
| SqliteStore 技术探针 | setup / put / get / search 全通过（临时目录，已删） | sqlite-store-probe.log |
| Git | `refactor/memory-auth-v1` @ `5851e91`；Phase 1 未提交修改全部在位 | git-status.txt |

Agent / Saver / CaseContext 链路**零失败**。RAG 唯一问题确认是环境资产缺失，不是逻辑错误（验证计划第 4 节三条前提逐条核实通过）。

---

## 对执行计划的直接影响

1. **Batch 0 的 Phase 1 baseline 依赖已闭合**（本验证即 baseline，无需重跑）。
2. **Entity Gap 8 问全部为"无"**：Batch 1（DDL + 种子）可按计划建表，无既有实体需要调和，不存在隐藏的业务表。
3. **上轮指出的必修项仍然开放**：执行计划缺 "CaseContext → 新表" 字段映射整节。具体缺口：
   - `age` → `birth_date`（类型转换）
   - `gender`「男/女」→ `sex`「male/female」——枚举值不一致，会撞 CHECK 约束
   - `smoking_history` / `family_history`：原定进 Store，但 V0 不建 Store，**无落点**
   - `detection_completed` 的替代字段 `attachments.analyzed_at` 未定义
   - `clinical_notes` 在 V0 无表承接
   - `nodules` 各字段只能塞 `attachments.payload_json`
   
   **Batch 5（findings/attachments/reports）前必须补齐映射表，否则卡住或返工。**

---

## 环境事实（实施 Agent 必须知道，否则会误判测试结果）

1. **pytest 必须加 `--basetemp=<项目内目录>`**：本机 `%TEMP%\pytest-of-Lenovo` 目录权限损坏（WinError 5），默认 tmpdir 会把依赖临时目录的测试记成 ERROR（假错误）。
2. **日志采集方式**：PowerShell 5.1 下 `run_tests.ps1` + `Tee-Object` 产生 UTF-16 乱码日志；直接 `python -m pytest > file 2>&1`。
3. 解释器：`D:/agent_martin/conda/envs/medical_ai_agent/python.exe`（Python 3.10.21，langgraph 1.2.0 / checkpoint 4.1.0 / checkpoint-sqlite 3.1.1，FastAPI 0.141.1）。
4. `DEEPSEEK_API_KEY` 由 Martin 本地提供（**不写入任何文档/git**）；验证期间仅作环境变量占位，未发起真实 LLM 调用。live API 验证属后续专项（验证计划 §22）。

---

## 移交的风险（不阻塞 GO，但需带进 Batch 计划）

1. **BGE 模型缺失**：RAG 6 项（test_integration×3、test_one_click×2、test_knowledge_manager×1）本机不可验证；网络可达或离线放置模型到 HF 缓存后需补跑。
2. **tests/test_monai.py 假阳性设计**：缺权重（`models/lung_nodule_ct_detection-0.6.8/models/model.pt`）+ 缺测试数据（`data/*.nii.gz`）时静默 return 记 PASS，6 项中 4 项空转。建议后续阶段改 `pytest.skip()` 显式跳过（本轮按验证计划未动）。
3. 验证 Agent 明确未做（留给实施阶段）：git commit、任何生产/测试代码改动、app.sqlite 创建、BGE 下载。

---

## 开工指令

从 Batch 1（DDL + 种子数据）开始，遵守 `MARTIN_ENTITY_V0_EXECUTION_PLAN.md` 全部约束；每 Batch 完成后对照其验收清单。唯一前置补课：先落字段映射表（见上），再动 Batch 5。
