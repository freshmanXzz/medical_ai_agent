# 路线图（ROADMAP）— 2026-09-30 定稿

原则：只列已确认的事实与待办，不编造未定义的阶段范围。V2 的具体分批由实施 agent 依据执行计划提出后再补进本文件。

## 当前基线（已完成，验收记录在 docs/refactor/）

| 阶段 | 状态 | 关键数字 |
| --- | --- | --- |
| Entity V0（业务实体/授权/事实链/checkpoint 联动） | ✅ ACCEPTED | 全量 229 passed / 0 failed |
| SqliteStore V1（跨 Thread 记忆） | ✅ ACCEPTED（2026-09-30 定验） | live A 8/8 / B 7/7 / C 5/5；离线 280 / 0 |
| 前端登录 + 服务端会话生命周期 | ✅ UI 端到端实测通过 | 登录→建会话→对话→记忆注入全通 |

## 近期（V1.1 小活，不依赖新模型资产）

1. **报告生成接业务 Finding 回填**：报告模板目前只消费检测结果（位置/尺寸/置信度），未上传 CT 时整段"未提供"，而病例事实里的位置/日期在 findings 表里。从 findings 回填 anatomy / observed_at / diameter_mm 到"影像所见"与"检查信息"。
2. **服务启停脚本化**：封装凭据注入 + `python -m martin web` 的启动/停止脚本，消除每次手写包装的重复。
3. **知识库实测**：本机 BGE 已装；上传指南文档 → 重建索引 → 对话检索引用进报告（当前 live 验收中"知识库未初始化"即为待测状态）。
4. **患者/病例发现入口（2026-09-30 查证的功能缺口）**：`POST /api/threads` 只收 `case_id`，但系统没有任何"发现"入口——`AccessRepository` 没有按医生列患者的方法，也没有 `GET /api/patients`；前端 `frontend/src/stores/chatStore.ts:37` 写死 `DEFAULT_CASE_ID = 'C002'`，`Sessions.vue`（标题"病例记录"、渲染 `thread_id` 并标注"病例标识"）与 `Dashboard.vue`（"历史病例记录"= 会话数）把**会话**当病例展示。即 **API 入口单元是病例、UI 入口单元是会话，两者之间没有桥**。修法：
   - 后端：`AccessRepository.list_by_doctor(doctor_id)` + `GET /api/patients`（`GET /api/patients/{patient_id}/cases` 已实现）；
   - 前端：落地页改为"我的患者 → 病例列表"，选中病例才创建会话；现有会话列表降级为"某病例下的历史会话"；
   - 文案：修正"病例标识 · {thread_id}"与"历史病例记录"（当前界面用"病例"指代 thread）。
   - 约束：患者身份只能由 `thread → case → patient` 反查得到，**不得由模型从对话文本推断**（同 Entity V0 决策 3 对 doctor_id 的禁令）。若日后要做"按特征找患者"，检索范围必须先被业务授权收窄、只输出候选、由医生确认后才建会话。
5. **授权关系写入出口**：`doctor_patient_access` 目前只能由 seed 脚本和测试写入——`AccessRepository.grant()` 无 service 方法、无 HTTP 端点，"谁在什么条件下把患者授权给医生"尚未设计（`revoke` 同理）。需要管理端点或 CLI（含 `case_change_audit` 审计），否则除 seed 之外没有任何患者能进入医生的工作台。

## 全链路实测（需 MONAI 权重与 CT 影像的机器）

- 前置：权重摆 `models/vision/lung_nodule_ct_detection-0.6.8/`（双层嵌套）+ 本地 MinIO（localhost:9000）。
- 验收线：UI 上传 CT → 检测出结节（真实位置/直径/置信度）→ findings 落库 → 报告被真实数据填充 → 阅片渲染。
- 附带：`tests/test_monai.py` 当前在缺权重时静默跳过（历史遗留假阳性），本轮顺带改为显式 `pytest.skip()`。

## 中期（V2）

- 范围以 `docs/plans/MARTIN_ENTITY_V0_EXECUTION_PLAN.md` 的阶段定义为准，启动前由实施 agent 出分批计划补入本文件与 REFACTOR_PROGRESS。

## 远期（方向，未排期）

- 在线 demo：部署至个人服务器供交互访问（受安全组/HTTPS 限制，需先补 443 规则与证书）。
- 多医生协作深化：授权审批流、病例分享审计报表。
