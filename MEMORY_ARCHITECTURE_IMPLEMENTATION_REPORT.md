# Martin 长期记忆架构实施报告

日期：2026-10-02。分支：`refactor/memory-auth-v1`。
执行依据：用户明确要求按 `MARTIN_LONG_TERM_MEMORY_PLAN.md` 实施，并批准发送
项目系统 Prompt 与隔离合成数据到现有配置的模型端点进行真实 LLM 验收。

## 当前架构审查与阶段顺序

业务修改之前完成 [CURRENT_MEMORY_ARCHITECTURE_AUDIT.md](CURRENT_MEMORY_ARCHITECTURE_AUDIT.md)。
先核对源码与真实 SQLite 元数据，再完成 V1.1 离线、真实 REST/WS 验收，之后扩展。
当前 V1.1 A/C 已有生产修复，本轮修复了不可跨机器复跑的验收工具，没有重写
既有偏好策略或已通过的 C002 6→8mm 来源链。

## Schema / namespace 与分类

业务库仍为原十表，未新增第二套医疗事实表、未执行数据库迁移。
保留 SqliteSaver/业务 Thread 一一对应关系及所有 V1 namespace/key。
新增 typed record namespace：

| namespace | 用途 |
| --- | --- |
| doctor / doctor_id / records | 有来源的医生偏好与工作流偏好 |
| doctor / doctor_id / patient / patient_id / records | 医生私有的患者讨论、决策、任务、纠正声明 |
| memory_vector / doctor_id / patient_id | 独立向量数据库中的派生语义投影 |

`models.py` 定义九种 memory_type。新持久记录保留 memory_id、type、四个身份 ID、
source_type/source_id、interaction_id、created_at/observed_at、status/confidence、
logical_key/supersedes、text/data。报告偏好在同一 Store batch 中同时保存 V1 value
和 typed provenance；旧调用者仍读原 `report_style` 字典。
患者事实/医疗观察由 SQL 只读投影，病例演变由结构化时间事件计算。
confidence=1 的事实投影表示来源行已确认，不代表诊断置信度。
旧私有备注和病例 key-value 保留兼容读取，没有静默重写旧记录。

## Retriever 实现

- Exact：授权后的 Business SQL 白名单事实 + 精确 Store namespace/key/type。
  医生偏好、工作流、correction、task 不依赖 embedding 或向量 Top-K。
- Temporal：confirmed Finding、UTC 解析排序、类型/部位/时间/source Finding/lesion ID
  过滤，剔除 draft/superseded/无效时间。时间和差值由代码确定。
  当前病例最新确认观察为 anchor，排除其他病例更晚的观察，防止未来数据被称为历史。
  单观察时间点比较保留 `lesion_identity_unconfirmed`；多个候选不自动配对。
  稳定 lesion_id 可形成明确多次随访链。
- Semantic：授权后限定 doctor+patient namespace，case/type/status/time 在 SQL
  Top-K 前限制；最低 cosine 0.45，轻量词项 rerank，去重，命中后回源并重新授权。
  默认只搜索 clinical_decision/historical_discussion；不进行跨患者搜索。

## Memory Router 与 Prompt

`MemoryRetrievalRouter` 统一执行：身份/Thread 与患者授权 → 意图计划 → 三检索 →
来源校验 → 去重/排序 → MemoryContext → 动态 System Prompt → 模型。
REST 和 WebSocket 已接入同一 Router，不改变浏览器公开 ChatRequest/Response。
混合“为什么上次观察、现在变化如何”调用 Temporal 与 Semantic，同时保留 Exact。
半年查询使用当前病例观察日期锚定结构化六个月时间窗；显式时间过滤支持 UTC。
Prompt 保留原 V1 分区，并增加检索计划、事件、差值、语义讨论、合并来源和局部状态。
片段作为数据，不能执行其中的指令，也不能作为医学指南证据或当前确认事实。

新增 API：

```text
GET  /api/memory/threads/{thread_id}/records
POST /api/memory/threads/{thread_id}/records
POST /api/memory/threads/{thread_id}/retrieve
```

身份从认证取得；患者/病例坐标由业务 Thread 解析，传入不一致坐标拒绝。
匿名 legacy CLI 不获得患者私有记忆权限，原有 checkpoint 行为保留。

## Memory Writer

`MemoryWriter` 选择有类型、有来源的值得保存片段，不写整段聊天或 reasoning。
登录 Agent 增加 `save_long_term_memory`，text 必须逐字来自本轮原始医生输入；
附件系统 guidance 单独传递，不能伪装医生原话。真实 HumanMessage ID 作为来源。
明确决策、任务、讨论、纠正、工作流分别保存，报告偏好仍由专用工具保存。
API 允许医生显式提交已选片段，禁止直接写 patient_fact/medical_observation/case_evolution。
纠正声明统一标记 business_fact_updated=False，不自动改变确认事实。

相同内容去重；同 logical_key 更新以 Store atomic batch 写入 superseded lineage。
不同病例的临床决策不会因相同逻辑 key 自动覆盖旧病例决策。
源写失败抛出；语义索引失败返回源已保存/索引不可用，并允许之后从源重建。
报告和记忆保存同时失败时进行受保护的单次输出修复，不能保留乐观成功声明。
新记忆工具的运行/审计日志仅保留类型，不重复保存医生片段或完整思维链。

## Vector index 设计与知识 RAG 隔离

本机已安装 LangGraph 1.2.12 / checkpoint-sqlite 3.1.1 / sqlite-vec 0.1.9。
安装源码和 native 内存探针证实 SqliteStore 已满足 index/query/filter 功能。
复用原生实现，独立 `data/memory_vectors.sqlite`，配置变量为
`MARTIN_MEMORY_VECTOR_DB_PATH`；仅 `text_fields=['text']`，512维本地 BGE、cosine。
不使用 RAG 全局 Chroma singleton，不在医学知识 collection 内混查患者记忆。
路径拒绝与业务库、源 Store、Saver、知识 Chroma 文件碰撞；支持自定义注入源库检查。
独立懒加载/锁/缓存/关闭；FastAPI shutdown 关闭向量连接。
失效源、删掉的 Thread、superseded 记忆不能从残留向量复活；缺向量可重建。
新增数据库与 sidecar 已加入 gitignore。

## 已修改 / 已运行 / 已通过

主要代码：`martin/memory/{models,scope,retrievers,vector_index,semantic,router,writer,
interaction,tools}.py`，以及 Service/Context、Agent Prompt/执行、REST/WS 接线和 shutdown。
新增三组记忆测试，更新原 API/消息表示契约测试；验收脚本均在 validation_scripts。
未改前端公开协议、MONAI、医学知识检索行为、模型配置或核心依赖版本。

| 验证 | 结果 |
| --- | --- |
| 修改前最小 V1.1 | 51 passed |
| 修改前完整基线 | 325 passed / 2 skipped / 3 CT 内存失败 |
| Exact / Temporal native SQLite | 16 passed |
| Semantic native SQLite/Chroma 分离 | 17 passed |
| 中间记忆/Agent/API 集成 | 105 passed / 1 skipped |
| 扩展后完整 suite 初跑 | 369 passed / 2 skipped / 4 failed；3 CT 原有内存失败，1 旧消息表示断言已修复 |
| 最终可运行全套回归 | **375 passed / 2 skipped / 3 deselected**；仅排除上述已证实的 3 CT 场景 |
| 最后来源元数据/API 专项 | **108 passed / 1 skipped**；覆盖病例演变来源封装与关闭连接 |
| 真实 BGE 离线写入/搜索 | PASS；相关决策 score 0.6238，无关讨论不召回 |
| AST / 差异检查 | 修改代码 AST 通过；本轮差异无 whitespace 错误；用户既有 AGENT.md 空白问题保留 |

主要复跑命令（先显式配置项目解释器或激活已选择环境）：

```powershell
& ./scripts/run_tests.ps1 -PytestArgs @('tests/memory', '-q')
& ./scripts/run_tests.ps1 -PytestArgs @('tests', '-q', '-p', 'no:cacheprovider')
# 本机原有三项 CT 内存失败单独记录，不能将 deselected 称为通过。
& $env:MARTIN_TEST_PYTHON validation_scripts/store_v11_live_acceptance.py
& $env:MARTIN_TEST_PYTHON validation_scripts/memory_architecture_live_acceptance.py
```

## Live LLM acceptance

首次沙箱调用被网络策略阻止，保留真实 FAIL 证据；用户明确批准之后才联网重验。
验收使用真实 REST/WS、真实模型、真实 Store/Saver、真实本地 BGE，所有业务/记忆/
checkpoint/vector/知识/对象路径均隔离；仅 Alpha/Beta 合成数据，禁止影像工具访问。
记录实际模型输入/公开回答与真实 Store/Router 返回，剥离 reasoning 和凭据。

V1.1 放行验收：15 次真实调用，无模型连接错误。A 三线程分别 127/113/93 字符，
全部结论前置、≤200字符、毛刺重点；B 正确 6→8mm/+2mm；C REST/WS 无伪造历史。
三检索首验：真实 Agent 分别保存 decision/task，跨 Thread REST/WS 同时召回 decision
及 SQL 差值，score 0.6299；doctor B 拒绝且不读取 Store；仅 index 故障时 Exact/Temporal
继续，模型说明原因不可检索，并注明未确认同一病灶。之后修复旧病例未来观察边界。

最终代码在两个全新进程中顺序重验：

| 验收 | 真实调用 | 结果 |
| --- | --- | --- |
| 三检索扩展 | 8 | Writer、组合 REST、组合 WS、旧 C001 时间边界、越权隔离、仅语义索引故障六组结构检查与公开回答语义复核全部通过 |
| V1.1 A/B/C | 15 | A 三线程报告 110/177/139 全字符，均结论前置、≤200、毛刺重点；B 6→8mm、观察值差2mm；C REST/WS 明确历史不可用，保留当前8mm分析且不编造历史 |

最终组合回答注明历史讨论不是确认事实，同部位观察差值没有证明同一病灶。
旧 C001 上下文与公开回答仅保留当时当前6mm，不混入后来 F002/8mm。
单独语义索引故障时，实际源 Store 正常，Exact/Temporal 继续；模型不猜测观察原因。
两轮模型连接错误、影像工具调用和配置凭据内容扫描命中均为零，隔离 API 服务均关闭。
每轮的 evidence.json、manifest.json 和 semantic_review.json 保留于本机产物目录；
语义复核记录原始证据 SHA256，并逐项检查公开回答。机器路径见 LOCAL_NOTES.md。
脚本结构输出中的 REVIEW 由上述独立语义复核落为 PASS；该结论限定本轮记忆行为，
不等于全面临床判断验收。V1.1 C 仍出现未经本轮知识检索验证的泛指南旁述，另记为限制。

## 已知限制 / 尚未验证

1. 完整 suite 的三项真实 CT 测试在修改前后均 CPU 重采样内存不足；检测设备 CUDA
   可用，不能将该失败描述成 GPU 不可用。独立复跑超时中止，没有宣称真实 CT 通过。
   旧视觉测试亦有捕获异常后无断言返回，不构成完整 MONAI 成功证据。
2. 为保留 V1.1 C 保守合约，源 Store 故障时 Router 不从 SQL 自动恢复纵向历史；
   当前 SQL 事实仍可分析。仅向量索引故障时 SQL Temporal 正常继续。
3. 本轮没有业务稳定病灶 ID migration；同部位单观察差值不证明同病灶生长。
4. 临床自然语言片段的分类由明确工具调用/医生 API 提交完成；没有全聊天自动抽取。
   医疗事实须经业务写入确认；correction 召回声明不等于已应用医疗事实纠正。
5. 同进程写锁和 native atomic batch 保证本批 revision 一致；跨进程并发同 key 不提供
   独立 CAS/version 竞争控制，跨业务/Store/向量库也不提供分布式事务。
6. 固定语义阈值不能证明所有检索都相关；目前用类型范围、来源、预过滤和轻 rerank。
   embedding 模型更换需要重建派生索引；未做复杂 consolidation/遗忘/大型 reranker。
7. 现有 legacy 工具与日志仍有超出本轮记忆链的隐私/指南旁述风险，详见 Phase 0；
   live 验收不冒充全临床安全、真实知识库指南或 MONAI/MinIO/UI 全链路验收。

## 下一步与工作树交接

按当前计划范围完成 SQLite 三类检索后，下一步是另行处理真实 CT 预处理内存、
明确稳定病灶身份，以及更广泛临床来源纪律验收；未启动 PostgreSQL/全局患者搜索。
源码、测试、验收脚本、计划与报告作为本次提交交付，包含既有源码和文档调整。
Martin 已明确要求推送实施分支、合并至 main 并推送；实际同步状态以 Git 为准。
本机会话记忆、运行产物和凭据保留在本机，不纳入提交。
可复跑脚本已入仓库目录，运行库/模型/日志/凭据不作为源码交付。
本机解释器路径、运行产物位置及临时服务状态仅写 git-ignored LOCAL_NOTES.md。
