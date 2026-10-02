# Martin 当前长期记忆架构审查（Phase 0）

日期：2026-10-02。分支：`refactor/memory-auth-v1`。
本报告在本轮业务代码修改之前完成。审查了 `martin/`、`api/`、
`tests/`、`scripts/`、`validation_scripts/` 和 `docs/refactor/` 的相关实现。
保留工作区已有 `.gitignore`、`AGENT.md`、`martin/config.py` 修改与其他用户文件。
没有初始化、迁移或读取正式患者数据；实际数据库检查只读 schema 元数据。

## 1. 当前数据库表和关系

业务库默认 `data/app.sqlite`（`MARTIN_APP_DB_PATH` 可覆盖），事实与授权唯一来源。
`martin/db/schema.sql` 定义以下十表；各实体主键为 TEXT ID，repository 默认生成 UUID。

| 表 | 主键 / 唯一 | 外键及删除行为 | 时间字段 |
| --- | --- | --- | --- |
| users | id；username UNIQUE | 无 | created_at / updated_at |
| patients | id | 无 | birth_date / created_at / updated_at |
| cases | id | patient_id → patients RESTRICT | age_recorded_at / created_at / updated_at |
| threads | id | doctor_id → users RESTRICT；case_id → cases RESTRICT | created_at / updated_at |
| doctor_patient_access | (doctor_id, patient_id) | 两端 CASCADE | created_at |
| attachments | id；(case_id, storage_path) UNIQUE | case CASCADE；uploaded_by SET NULL | analyzed_at / created_at |
| findings | id | case CASCADE；source_attachment_id、created_by SET NULL | observed_at / created_at / updated_at |
| reports | id；(case_id, version) UNIQUE | case CASCADE；created_by SET NULL | created_at / finalized_at |
| auth_sessions | id；token_hash UNIQUE | user_id CASCADE | created_at / expires_at / last_seen_at / revoked_at |
| case_change_audit | id | actor_user_id SET NULL；target_id 无外键 | occurred_at |

状态约束：Finding 为 draft/confirmed/superseded，直径非负；报告版本 ≥1，
状态为 draft/final/superseded；授权为 read_only/read_write；用户仅 doctor，
有 is_active；病例年龄 0–130。连接均开启 foreign_keys、busy_timeout；初始化使用 WAL。
`init_schema` 通过幂等建表及补列兼容旧库，没有 schema-version 表。
自动时间为 UTC ISO；observed_at 是未经严格规范化的 TEXT，现有 SQL 按字符串排序。

当前本机默认业务库和 memory.sqlite 不存在，不能将 DDL 描述为已存在的运行数据。
已有 `data/sessions.sqlite` 的表为 checkpoints/writes；已有测试 Chroma SQLite，
只检查内部表结构，没有读取患者内容。

认证链为 Cookie → opaque session 的 SHA-256 查验 → active DoctorIdentity →
业务 AccessService。患者必须有 grant，病例回查患者，Thread 还必须属于当前医生。
write=True 必须 read_write；repository 自身不授权。Thread 元数据列表的患者授权
不等于读取其他医生 checkpoint/private memory 的授权。

## 2. 当前 SqliteStore namespace 与 Saver

Store 在 `martin/memory/store.py` 初始化：`SqliteStore.from_conn_string` + setup，
默认 `data/memory.sqlite`，由 `MARTIN_MEMORY_DB_PATH` 覆盖，尚未配置向量 index。

| namespace | 内容 / key |
| --- | --- |
| doctor / doctor_id / preferences | report_style 等医生偏好 |
| doctor / doctor_id / patient / patient_id / private | 医生私有患者备注 |
| patient / patient_id / memory | observation:finding_id |
| case / case_id / memory | 病例 key-value 记忆 |

所有旧 value 不是统一 memory envelope，缺 memory_type/source_type/confidence 等字段。
患者观察保留 finding_id/source_case_id/finding_type/anatomy/diameter_mm/observed_at/status。

Saver 默认 `data/sessions.sqlite`，可通过工厂参数指定，进程 singleton 复用。
业务 threads.id 就是 LangGraph configurable.thread_id，没有跨库外键。
checkpoints 主键为 (thread_id, checkpoint_ns, checkpoint_id)，writes 还含 task_id/idx；
两表没有外键。删除业务 Thread 先删并确认 checkpoint；跨数据库不具备原子提交。
CLI 的 legacy Thread 不一定存在业务行，不得据此赋予患者记忆权限。

## 3. 当前记忆读写链路

`MemoryService` 在读写前校验 active doctor 或患者/病例/Thread 业务授权。
偏好由 `/memory/preferences/report-style` 或 `save_report_preference` 工具显式写入。
私有备注和病例记忆已有 service 入口，尚无分类 Writer。
`sync_finding` 只投影 confirmed Finding，key 由 Finding ID 决定。
`snapshot_for_thread` 先授权，再读取当前 confirmed Finding，再执行 Store search。
每次 reconcile 由 Business Finding 重建观察投影并清除失效 observation key；
历史返回来自业务事实，不是脱离业务库单独恢复的 Store 历史。
Store 故障返回 available=False，保留当前业务事实。

业务事实链由 FactService 保存附件、Finding、临床字段及报告；source_attachment
必须属于相同 case。检测一结节一行，重复检测目前不会自动去重/supersede。
报告工具优先读取当前 confirmed Finding，旧 checkpoint 只作为无 Finding 的兼容回退。
报告生成和报告持久化是不同入口。

## 4. 当前 Prompt 注入链路及 V1.1 状态

REST 与 WebSocket：认证/Thread 授权 → MemoryService snapshot → create_agent →
memory_prompt/report_preferences → dynamic_prompt → 模型 → 输出偏好校验 → checkpoint。
MemorySnapshot 分离 CURRENT CASE FACTS、DOCTOR PREFERENCES、PRIVATE NOTES、
PATIENT HISTORICAL MEMORY、CASE MEMORY 和 MEMORY STATUS。
已授权白名单报告偏好单独提升为格式约束，优先级低于事实/医疗安全/当前任务。
输出超长或非结论前置时最多进行一次无工具重写，检查测量/日期/失败锚点。
Store 故障不会在模型之前提前 503，真实模型接收历史不可用声明。

计划 Phase 1 的 A/C 已在当前源码修复，9月30日记录为 live 通过；本轮仍重新验收。
本轮修改前最小离线基线：`tests/memory` + missing-measurements，51 passed。
已有 live 脚本仍带旧机器目录/Conda 凭据加载，V1.1 有未定义 chinese_length 且不跑 B，
须先修验收工具，不能直接复用旧报告宣称本轮通过。

## 5. 当前 RAG 向量链路与版本能力

KnowledgeManager → loader → splitter → 本地 BGE embedding → LangChain Chroma →
query/detection retriever → 带 source metadata 的知识结果 → retrieve_knowledge。
默认 collection `medical_knowledge`；路径由 CHROMA_PERSIST_DIR 配置，默认 ChromaDB。
当前配置路径无已初始化知识 collection，不能宣称医学知识检索已运行通过。
BGE 为本地 bge-small-zh-v1.5，512维、normalize_embeddings；CPU 离线真实嵌入已验证。

已选项目 Python 3.10.20、SQLite 3.51.2；langchain 1.4.3、core 1.6.6、
langgraph 1.2.12、checkpoint-sqlite 3.1.1、chromadb 1.5.9、sqlite-vec 0.1.9。
以**安装源码和内存运行探针**确认 SqliteStore 支持 index、query、metadata filter、
sqlite-vec cosine。namespace 与 metadata 在 SQL WHERE 内先限制，随后评分和 LIMIT。
正确字段配置为 `text_fields=['text']`；默认 `$` 会嵌入整个 JSON，不适合此计划。
合成内存探针证实另一 namespace 的高相似结果不进入 Top-K。
扩展可复用 native SqliteStore，无需另装或升级核心库。

## 6. 已结构化的信息

身份/授权、患者 sex/birth_date、病例年龄/吸烟史/家族史/备注、附件来源、Finding
类型/部位/直径/观察时间/状态、报告版本已在业务库。明确事实优先 SQL 精确检索。
医生报告偏好固定 key；业务 Finding 可投影为只读 medical_observation。
case_evolution 应从时间事件算得，不另造一份事实。

## 7. 适合增加语义记忆的信息

医生明确表达的 clinical_decision、historical_discussion，以及必要的工作流经验。
不能向量化整段聊天、数值事实、报告正文、知识检索全文或模型 reasoning。
语义记忆须含医生/患者/病例/Thread、来源与时间，仅在当前获授权患者范围搜索。
医生私有讨论即使另一医生也有患者授权仍不可见。

## 8. 时间事件链需求

时间解析/排序须由代码完成，过滤 draft/superseded，区分 historical/current，
保留 case_id/source_finding_id/type/location/observed_at，再形成可追溯差值。
只有明确匹配病灶才可计算变化。当前 schema 没有跨检查稳定 lesion_id；同部位及
payload.index 不足以确认同一结节。单一候选可展示带匹配限制的观察比较，多个候选
必须标注歧义、不给自动差值。无效时间也必须报告，不由 LLM 猜时间顺序。

## 9. 与计划的冲突、现状风险及实施决定

缺统一分类、retrievers、router、writer、dedup/supersede lineage；旧 value 无统一来源。
snapshot 同时做授权/Store重建/检索/投影，不能独立验证三种检索器与局部故障。
Store 的 observation 是缓存，Business DB 必须继续作为事实源。
Agent update_case_context 当前可能只改 checkpoint，不能自动提升为确认事实。
现有 legacy 日志/审计代码仍写 reasoning/user text，与项目最小日志规则有冲突；
新记忆不读取这些日志、reasoning 或模型推理作为来源，验收禁用该日志。

实施：保留旧 namespace/key 和 V1.1 合约；新增带来源的 typed records；
建立统一业务授权 scope；Exact 使用 SQL/Store，Temporal 使用 confirmed SQL 事件；
Semantic 使用独立 `memory_vectors.sqlite` 原生向量 Store 与专用 namespace，
仅索引文本字段，回查有效记录/当前授权。医学知识 Chroma 不接收患者记忆。
Router 合并去重并标注各检索器状态；Writer 只接收有明确类型/来源的值得保存片段，
医疗事实仅由业务行派生。保留失败可检测、当前病例可继续的行为。
不实施 PostgreSQL、跨患者搜索、复杂 consolidation、遗忘或大型 reranker。

Phase 0 到此完成；之后先重跑 V1.1 live + 全量回归，通过后才扩展业务架构。
