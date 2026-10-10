# Martin 长期记忆 V2.2 实施与验收

验收日期：2026-10-10。执行依据：[已确认执行方案](../plans/MARTIN_MEMORY_V22_EXECUTION_PLAN.md)。范围为隔离合成数据的记忆治理、模型上下文和工作站操作；真实 CT、Stable Lesion ID、临床有效性、多 worker 部署属于后续独立验收。

## 1. 基线与 Git

本节和第 13 节记录的是实施验收结束、提交授权之前的 Git 状态。用户随后于 2026-10-10 授权提交并推送；发布分支与跨机器接续见 [开发交接说明](../plans/MARTIN_MEMORY_V2_DEVELOPMENT_HANDOFF.md)，实际提交及远端状态以 Git 记录为准。

- 审查及交付分支：`codex/memory-v21-governance`；HEAD：`b8fd8b385f3de6d467c7fe7b364b12f800ba1c6c`。
- V2.1 实现尚在未提交工作区。实施前保存了 34 个相关文件、完整 tracked patch 和 SHA256 清单：`tmp/v22-baseline-20261009/`。Prompt 对比使用该快照的原 V2.1 Router，并校验哈希；没有把 Git HEAD 当作已验收 V2.1 源码。
- 本轮先复跑 V2.1 相关测试：340 passed、0 failed、2 warnings，84.72 秒。其历史模型证据不计入新的 V2.2 模型次数。
- 保留已有 `MARTIN_LONG_TERM_MEMORY_PLAN.md` 修改及未知 data/output/tmp、资料和脚本。未重置、清理、迁移真实运行库；未提交、未推送。
- 详见 [现状及安全基线](MARTIN_MEMORY_V22_BASELINE.md)、[V2.1 验收报告](MARTIN_MEMORY_V21_ACCEPTANCE.md)。

## 2. 现有能力与本轮新增

| V2.1 已有 | V2.2 扩展 |
| --- | --- |
| 九类记忆、Selective Writer、Exact / Temporal / Semantic、独立向量索引 | 低风险等价去重与来源强化，高风险相似记录独立保存 |
| provenance、revision / retraction、生命周期过滤 | 派生摘要、来源指纹与版本、失效传播、持久化幂等治理队列 |
| SQL Finding 权威、历史观察、未核实纠正和冲突 | 每轮极简背景、按需摘要、受保护事实与冲突两侧、分阶段完整性检查 |
| Agent / 报告 / REST / WS、记忆管理抽屉 | 最终 payload 统一预算、软配额、调用限制、可解释 trace |
| 医生 Cookie 认证及患者授权 | 默认关闭的 budget_admin 能力、配置校验/版本/审计/回退和管理 UI |

保持原 Python、BGE、Chroma、SQLite/LangGraph Store 和方舟模型配置，没有增加外部队列或替换模型。用户额外确认了两点：来源不明旧 case memory 保留但阻断正常注入；管理员沿用 doctor 身份增加独立能力，不扩大患者权限。

## 3. 风险分级去重

`deduplication.py` 扩展现有 Writer。自动近重复合并采用有限的等价表达规则，先检查同一 scope、类型与命题；条件、数字、否定或新增信息不同即独立保留。没有使用固定 embedding 相似度作为临床等价判据。

- 低风险偏好完全重复或支持的同义表达：保留一个 active 记录，追加真实来源到 reinforced_sources，并对各来源执行资格校验。
- 条件细化，例如普通报告字数限制与复杂病例详写：不被同义合并吞掉；显式修订沿用 V2.1 目标记录 supersession。
- 临床决策、声明及讨论：不同日期、病灶、理由及无法确认同一性的记录独立保留，不因文字相似确认医疗事实。
- Assistant 推测、临床 claim 与确认 Finding 的权威不因重复改变。治理不物理删除原始业务观察。
- 新 case memory 绑定医生、患者和病例；无可确认医生来源的旧条目保留原数据，正常 Prompt / 摘要阻断并记录 source_unknown。

## 4. 摘要生命周期与两级注入

摘要是可重建的派生讨论背景，使用确定性抽取，不进行额外 LLM 总结。只取当前医生在授权患者/病例范围内仍 active 的 clinical_decision / historical_discussion。保留原文、日期、病例、源 ID、源版本/指纹；不摘要 Assistant、未核实 claim 或其它摘要，不生成新诊断事实。

- successful write 只入队，达到条数或规模阈值后由响应 BackgroundTasks / WS 后台处理；请求路径不同步重建。
- 持久化 job key 与源版本/策略版本绑定；支持幂等、CAS、有限重试及周期 CLI。后台失败记录类型和状态，不复制原始来源正文到运行日志。
- materialize 逐项重读权限、active 状态、provenance 和指纹；缓存命中不绕过源校验。
- 撤回/替代立即使旧摘要 stale 并强制排队，即使有效数量已低于原阈值。重建前用有效原始来源或明确降级。
- 极简背景取授权 SQL 的性别、出生日期/检查时年龄、吸烟/家族史及来源日期；没有患者上下文时不强行注入。
- 详细摘要按历史、原因、随访任务需要注入。按完整片段选取，不从中间截断文字；明确记录 omitted / newer source IDs。
- 只有已入选且再次通过验证的摘要才能覆盖相应非 protected 原始讨论；未入选、待重建或失效摘要不能抑制原始证据。

持久化队列不等于已部署常驻 worker。进程重启后的周期补偿需要运维显式执行 CLI；本轮未创建系统计划任务。

## 5. 统一预算、关键内容和分阶段处理

`context_budget.py` 在请求级 ContextVar 中记录所有 Agent、工具报告、格式修复和独立报告调用。ChatOpenAI 同步/异步/stream 以及旧 HTTP 客户端在发送最终序列化 payload 前执行硬限，含 system、消息角色、完整 tool arguments/results、绑定 schemas 和输出预留。

计数口径分开标注：同主机标准 `/api/v3/tokenization` 的文本 BPE + framing 为估计，不是 Chat 计费精确数；provider actual usage 单独记录。Coding Plan 路径 tokenization 返回 404，故使用已实测的标准路径。分词故障回落 UTF-8 字节保守上界；未知模型窗口明确降级，不静默换模型。tokenizer 超时受请求剩余时限限制，无自动重试，缓存只在本请求内保存哈希与计数。

默认开发保护参数，尚不代表生产优化值：

| 项目 | 默认值 |
| --- | ---: |
| 应用总上下文硬上限 | 65,536 |
| 输出预留 / 安全余量 | 4,096 / 2,048 |
| 可用输入 | 59,392 |
| 极简背景 / 详细摘要预算 | 512 / 2,400 |
| 摘要触发条数 / 规模 | 12 / 12,000 |
| 最大阶段批次 / 阶段总量 / 请求时限 | 4 / 131,072 / 30 秒 |

方舟模型窗口与应用较小硬限分开；模型 profile 的官方依据及核对日期见源码 `MODEL_WINDOW_SOURCE` 和基线报告。配置范围由后端限制，不能关闭硬限。

| 任务 | RAG | memory | summary | history |
| --- | ---: | ---: | ---: | ---: |
| 问答 | 40 | 20 | 10 | 30 |
| 报告 | 35 | 25 | 15 | 25 |
| 随访 | 15 | 40 | 30 | 15 |
| 默认 | 25 | 25 | 20 | 30 |

软配额只分配弹性池，可借用空闲份额；最终输入仍受统一硬限。当前问题、安全/权威规则、必要确认事实、必要时序和已识别冲突两侧受保护。旧会话按完整轮次及工具配对投影，原 checkpoint 不删除。独立报告保留全部结节的结构化来源，brief 展示限制不等于静默丢弃其它结节。

超预算的 protected typed evidence 分批确定性读取、投影必要字段及来源，不另行增加模型概括调用。批次、总量和时间均有界；完整性不足返回“未完成完整分析”并显示已处理/未处理数量，授权 trace 列出 processed / omitted references，不伪装为完整结果。无法压缩的当前问题也走明确降级。

trace 记录选入/省略、duplicate、covered_by_summary、预算不足、状态/权限/来源失效、阶段结果和估计/实际 usage，不复制临床正文。报告与 Agent 发送前重新核验源，尤其是 tokenizer 返回之后的再次检查。

## 6. 并发与日志边界

本进程模型发送 guard 与 memory 生命周期变更、业务 transaction 共享 reentrant lock。校验可在同线程读 SQL，其他线程的事实/权限提交须等待 guarded dispatch 完成；tokenizer 内同线程变更仍会被返回后的校验拒绝。模型超时和异常会释放锁。

这会串行化本进程 SQL transaction，包括读事务，最长等待受请求上限影响。该保证只覆盖本进程按既有 transaction / lifecycle 出口进行的访问；不保证外部直接 SQL 或多个 server worker 的串行化。当前按单 worker 验证，多进程需 V2.3 专项证据与设计。

报告检索、模型异常和模板降级日志改为异常类型；新增 canary 断言错误正文不进入日志。公开预算异常是固定原因与处理数量，source references 留在授权 trace，provider 任意异常正文不回显。真实模型证据只记录合成 Prompt、公开回答、工具调用和数值 usage，不保留隐藏推理或凭证。

## 7. 管理员、配置 API 与 UI

users 增加默认关闭的 budget_admin 字段；兼容初始化做 additive migration。维护命令显式 grant/revoke 并原子写审计；HTTP 没有自行提升能力的接口。能力检查重新读 Cookie 对应医生，缺列、inactive 或数据库错误均 fail closed。

PolicyService 以 CAS expected_version 更新 current 和完整版本审计。严格校验整数、范围、输入/输出预算与各任务配额合计100；旧 schema、损坏/缺失/不可用策略回落 bounded default；回退产生新版本，允许目标0默认值，不覆盖历史。

前端只对“当前身份 capability + 服务端 can_manage”同时为真展示编辑。draft 与生效值分离，409 提示刷新，403 清除编辑；关闭、切换 thread 后忽略晚到数据。表单使用 novalidate，修复了 Element Plus 默认数字与原生 step 对齐不一致时保存被浏览器阻断的问题，合法性仍由应用和后端校验。

普通医生只能读取其授权 thread 的 trace。管理能力不额外授予患者数据、其他医生讨论或其他 thread trace 的访问权。

## 8. P0 与完整回归结果

解释器明确选用项目 Python 3.10.19。最终完整收集：**587 collected、572 passed、0 failed、15 skipped、0 errors、3 warnings，142.27秒，exit0**。产物：`tmp/v22-regression-20261010-122527-f7358920/`；完整转录：`tmp/v22-regression-final-complete-20261010-122527.log`。runner 没有 deselect 测试。

该全量运行期间真实模型暴露了正常 conflict 投影被误拒的问题：投影 status=conflict 与源 record status=active 不应进行同一结构的字段比较。修复保留源 active/provenance 验证，按 fresh finding_conflict 的全部字段比较；生产变更只在 Router 的这一分支。**全量结果不伪称修复后的同源码快照**：最后追加预算、governance、retrievers 三文件影响面验证，**79 passed、0 failed、0 skipped、2 dependency warnings，36.47秒**。新增真实 SQLite 正例确认正常冲突通过发送前 guard、独立报告执行合成模型调用；真实网络发送由第10节模型验收支持。源撤回或业务值变化的反例仍阻断且模型调用0。最终源码哈希和全量运行中变更记录见 coverage_summary / source manifests。

全量当时 memory 261通过，budget policy/context/API 102通过，新 DB 锁2通过；这些集合互有重叠，去重 union 为281通过、0跳过，不能相加作为额外测试数。本阶段相关确定性 P0 场景在全量与最后影响面回归中均零违规。

保留失败历史并修复，而不是删测试：

| 运行 | 结果 | 处理 |
| --- | --- | --- |
| 首次全量，563收集 | 544通过、4失败、15跳过 | 三项旧 Prompt 标签断言改为实际 JSON/source/authority 断言；影像缺图校验先于模型创建，保留原409契约 |
| 第二次全量，583收集 | 567通过、1失败、15跳过 | CLI子进程UTF-8输出与父GBK解码不一致；测试显式固定两端UTF-8，不改变产品输出 |
| 最后全量，587收集 | 572通过、0失败、15跳过 | 全范围收集，原失败通过 |
| 最后 conflict 修复后影响面 | 79通过、0失败、0跳过 | 正常冲突、撤回、业务值变化及独立报告验证 |

三项保留 warning 是一项 Starlette 依赖弃用和两项旧 smoke test 返回非 None；CLI解码引发的 thread warning 已消除。前端构建的 bundle size / 第三方 PURE 注释提示单独列在第10节。

公开报告最后发现空知识占位被当作 REPORT RAG:0 编号，属 P1 来源展示缺陷。已阻止空占位进入 RAG BudgetItem，并在没有入选原文时禁止生成知识引用；有效原文仍保留来源。补充覆盖三类报告的空知识/有效来源正反例，并回归 Finding输入、缺失测量与预算：**114 passed、0 failed、0 skipped、1 dependency warning，17.30秒**；证据 `tmp/v22-regression-20261010-123700-6a4e9934/`。该修复也在第10节单独真实模型验证。79与114均是修复后影响面结果，与全量有重叠，不能相加虚报唯一测试数。

15项显式跳过：真实 CT/native detector/本地影像读取9项；未 mock 外部报告2项；已有真实库依赖或重复 embedding smoke2项；无 key 时不执行有效断言的旧 credential分支2项。确切 nodeid 与原因见 selection.json。独立真实模型覆盖合成记忆/报告部分，**未替代真实 CT/detector 链路**。本地 BGE + 原生 Chroma 合成 integration01/02 实际执行，其他归一化、结果保存、认证、权限、会话恢复、REST/WS和故障测试保留。

### 执行方案场景映射

下列按计划编号映射实际证据，不能从测试函数中的 T 编号直接推断覆盖：

| 计划场景 | 正常与边界/故障证据 |
| --- | --- |
| T01–T02 完全重复/同义 | growth_deduplication：源强化、重试、支持同义；Assistant/异 scope 拒绝、撤回不复活 |
| T03 条件细化 | 条件/否定/数字/新增信息独立保留；显式修订仅 supersede 目标 |
| T04–T05 临床理由/不同病灶日期 | 不同理由、日期、病例及未指定同一事件独立；相同结构化事件精确重复不提升权威 |
| T06 达阈值 | rolling_summaries：条数/规模排队、进程重开、幂等；队列失败不丢原文 |
| T07 撤回/并发 | stale原子传播、失败回滚、锁内并发读取、tokenizer期间变化、旧materialization拒绝 |
| T08 滚动来源 | 只使用raw、修订阻断旧版本、版本CAS/源变更；源图/投影篡改拒绝 |
| T09 两级注入 | 极简SQL背景与按需详细摘要；文本/背景源变更拒绝，无患者不强加 |
| T10 时效历史 | 2024历史Finding保持、过期任务过滤；治理前后原始观察与日期相同 |
| T11 多通道预算 | 最终payload角色/tool/schema/输出计数；闲置借用、tokenizer失败、未知模型及超限拒绝 |
| T12 关键冲突 | 冲突两侧protected；分阶段完整保留/额度不足明确partial；正常projection与源状态不混比 |
| T13 检索洪泛 | real SQLite vector+60条独立近重复、20条语义候选；2500预算保留F002/8mm/日期，duplicate/budget原因及逐项trace，原60条保留 |
| T14 任务差异 | QA/report/followup软配额不同但同硬限；summary未入选不能抑制raw，配置非法配额拒绝 |
| T15 多年分阶段 | 2024–2026四批源保留日期/值/病例/未确认关联；max1列出processed F0、omitted F1–3；旧checkpoint可恢复 |
| T16 vector/cache撤回 | memory_governance的stale semantic hit拒绝；summary cache、raw、偏好和tokenizer期间撤回/权限/Finding变化阻断 |
| T17 医生/患者隔离 | case_source_boundary、summary scope、trace、API授权；伪造source或共享病例不能读另一医生讨论 |
| T18 普通医生预算 | Cookie认证、API403、actor伪造拒绝；浏览器无配置编辑入口 |
| T19 非法值/回退 | 后端严格int/上限/配额、版本CAS、审计原子回滚；能力撤销、corrupt default及未知回退目标拒绝 |
| T20 故障 | Store保留SQL当前事实，semantic不编历史；summaryjob有限重试/CAS/恢复，配置不可用回落安全硬限 |
| T21 REST/WS/UI | 预算故障REST200/WS final明确降级；真实模型及独立报告、浏览器配置/只读trace（第10节） |
| T22 存量回归 | 全仓587项收集及15明确skip；V2.1来源/修订/声明/冲突/授权/会话和管理路径保持 |

对应主要文件：tests/memory/test_memory_growth_deduplication.py、test_memory_rolling_summaries.py、test_context_budget_v22.py、test_memory_v22_retrieval_flood.py、test_memory_case_source_boundary.py、test_memory_governance.py、test_budget_policy.py、tests/test_budget_api.py、test_app_db_dispatch_lock.py。

## 9. P1 基线与比较

### 9.1 可重复的 Prompt 投影对比

脚本：`validation_scripts/memory_v22_quality_baseline.py`；证据：`tmp/v22-p1-projections/comparison.json`。原 V2.1 工作区 Router 与新 Router 读取同一合成 snapshot，各渲染5次，包含确认8mm、历史6mm、待核实9mm冲突及12条讨论。计数为完整测试 payload 的 UTF-8 上界，不是计费 Token，不是整个旧 Agent 重放。

| 任务 | V2.1 输入估计 | V2.2 输入估计 | 变化 | 必要 atoms / 来源 ID 覆盖 |
| --- | ---: | ---: | ---: | --- |
| 问答 | 14,316 | 9,118 | -36.31% | 4/4；12/12 |
| 报告 | 14,322 | 9,124 | -36.29% | 4/4；12/12 |
| 随访 | 14,655 | 6,702 | -54.27% | 8/8；12/12 |

必要 atoms 的分母是脚本明确列出的值/日期/不确定性标记；来源覆盖是 ID 保留检查，不代表所有自由文本信息都已完整测量。有效 atoms 每千估计输入分别为0.439、0.438、1.194。两版都没有模型调用；正常3样本均无降级。

渲染中位时间分别为 V2.1 0.722/0.828/0.910ms，V2.2 1.692/1.660/0.932ms。问答/报告增加不到1ms，与模型或真实 SQL 检索时延不同；不据此建立整体时延 SLA。四源阶段样本在批次4时全部保留，批次1时明确 partial，未处理来源列出；模型调用0。

### 9.2 实际 Writer / SummaryService 治理测量

脚本：`validation_scripts/memory_v22_governance_metrics.py`；证据：`tmp/v22-governance-metrics-20261010-122018-591204/metrics.json`。使用真实隔离 SQLite、现有 Writer、SummaryService 和实际 Router budget item renderer。

| 指标 | 合成样本结果 |
| --- | --- |
| 等价重复消除 | 3/3组，减少3条；20次提交的原始来源20/20保留 |
| 支持的同义召回 | 2/2组 |
| 不同内容误合并 | 低风险0/3组；高风险0/4组 |
| 新增信息保留 | 7/7组 |
| 摘要有效源覆盖 | 4/4；完整文本/结构化字段保留 |
| 摘要片段漂移 / 误归因 | 0/4 / 0/4 |
| 限额摘要 | 1条选入、3条明确省略，四源均有覆盖账目 |
| 来源撤回 / claim / Assistant | 旧缓存拒绝；claim不摘要；Assistant来源拒绝 |
| 治理模型调用 | 0 |
| 原始 Business Finding | 保持不变 |

去重基线是同样20次输入的 append-only 计数，不能把3条减少全部称为相对 V2.1 的新能力（精确重复旧版已有）。同义覆盖只针对支持的规则，10组手工标注不推导总体误合并率。

摘要大小同时报告三种口径：原始记录封装3225，stored摘要5632，materialized摘要4294（内部源链开销使 materialized 增加33.15%）；仅渲染摘要文本1027。实际 Prompt 同口径比较，四条原始讨论3755 → 派生 summary budget item 2343，减少37.60%。不能用仅文本1027或另一个脚本的78.24%原文封装差作为完整摘要压缩率。

### 9.3 真实公开回答与阈值建议

同一实际授权 snapshot、相同问题、同模型与输出上限，各调用一次（仅比较两版 Prompt 投影，不重放旧 Agent）。方舟 actual usage：

| 指标 | V2.1 projection | V2.2 projection |
| --- | ---: | ---: |
| 实际输入 tokens | 7,533 | 4,301 |
| 实际生成 tokens | 1,261 | 1,621 |
| 总 tokens | 8,794 | 5,922 |
| 调用次数 | 1 | 1 |
| 总时延 | 8.791秒 | 10.402秒 |
| 必要测量值及状态 | 6/8/9均正确 | 6/8/9均正确 |
| 历史/当前/未核实来源、病灶关联不确定性 | 保留 | 保留 |

输入减少42.90%，总 Token减少32.66%；生成 Token增加28.55%，时延增加18.33%。这次未表现为更快，不能把输入缩减解释为时延必然改善。生成内容长度/数值 usage 差异同时存在，单次配对无法作因果归因或推导生产失败率；两个回答人工复核均未将历史值/提议升为当前确认值，也未确认同一病灶。无隐藏推理正文保留，只有 provider 数值 usage。

初始策略值保持开发保护值；支持的确定性样本要求关键 atoms/有效来源全部保留、误合并/漂移/误归因0违规，作为样本回归标准。尚无总体召回率、生产 P95、可接受失败率的证据，不设未经测量的生产门槛。

建议后续扩充按任务/医生/病例规模分层的固定语料，再定触发阈值及性能目标；先维持现有安全硬限。源指针封装的额外存储开销换取可复核性，当前 Prompt 缩减通过投影和避免重复注入获得。

## 10. 真实模型、REST / WS 与前端

使用既有火山方舟 / deepseek-v4.1-flash / Coding Plan 配置；没有替换服务、模型或泄漏 key。最终主链路运行 `tmp/validation/store-v1-live-20261010-123047-521620/evidence.json`，10次成功模型调用；最后空知识来源修复的单次报告验证 `tmp/validation/store-v1-live-20261010-123803-012569/evidence.json`。合计 **11次成功调用、7组28项检查全部true、7条公开回答/报告人工复核、关键边界0违规**（含2条P1配对回答）。raw evidence 的 REVIEW 标记保留，人工复核及答案/证据哈希另存 `tmp/v22-final-privacy/semantic_review.json`。

| 场景 | 确定性检查 | 公开回答复核 |
| --- | ---: | --- |
| A 摘要与历史来源，REST | 5/5 | 6mm历史与8mm当前分区；讨论不变确认事实；同一病灶未确认；摘要省略说明保留 |
| B 撤回后新thread，WS | 4/4 | 旧摘要拒绝，撤回标记在所有记录的消息角色/公开答复中均无；其余讨论不升权威 |
| C 冲突报告，Agent REST | 3/3 | 8mm仍为业务确认值，9mm待核实，未声称DB已改 |
| C2 独立report REST | 4/4 | 同样保留冲突与缺失资料；actual request-local usage已持久化；空引用展示另由F修正 |
| D 管理权限/审计/回退 | 5/5 | 默认关闭、同Cookie授予/撤销即时生效、回退为新版本，不扩患者权限 |
| E protected问题超限 | 2/2 | REST200明确未完成完整分析，chat model dispatch为0，不编完整报告 |
| F 空知识来源修复，独立report REST | 5/5 | 无虚构知识/RAG编号，无指南依据则不生成Lung-RADS/确诊；8mm/9mm边界保留，actual usage有记录 |

失败及中断的旧证据全部保留：首次异步摘要读取未等待job完成导致harness IndexError（已加有界轮询）；第二次E公共降级包装不一致（已修复REST/WS）；一次为补偏好撤回保护主动中断；一次C/C2正常冲突误拒（已修复并重验）。这些调用不计入最终11次通过次数，不把失败证据删除后称一次通过。

三层证据实际采集了 store/source lifecycle、实际调用的所有合成消息角色（含tool内容）及 trace、公开最终答复和 provider usage。跨会话B使用新thread；CT工具在harness中明确阻断；知识库为空、BGE实际加载、SQL/store/vector/checkpoint/object均独立。

前端 `npm run build` 最终通过（vue-tsc + Vite，1785模块，8.72秒）；保留第三方 PURE 注释及大于500kB bundle提示，不在本阶段更换依赖。真实 Vue setup/API adapter 定向检查 **8/8通过**，包括非法配额、CAS冲突、能力撤销、thread切换和关闭后的晚到结果隔离。

真实浏览器 **9/9操作检查通过**：合成管理员保存v1、回退生成v2并恢复30秒、非法101配额拒绝、审计历史、刷新 own trace；普通合成医生从授权病例记录恢复后只能看 own trace，没有配置编辑入口，列表不含另一医生session。浏览器 fixture trace 是预置合成记录，不能当作实际模型计费证据；实际usage见上述模型运行。检查清单：`tmp/v22-ui-20261009/browser_verification.json`。

截图与隔离 UI 数据位于 `tmp/v22-ui-20261009/`。管理员操作截图：`admin-budget-proof.png`；普通医生只读 trace 截图：`ordinary-doctor-trace-proof.png`。临时服务及本轮创建的浏览器页已关闭；未操作原浏览器页面。

## 11. 运维入口与可回退性

已有业务库初始化时添加字段，默认不授权。需要管理员时显式运行（用现有项目解释器、实际医生/库路径替换占位符）：

```powershell
python scripts/manage_budget_admin.py --db <business-db-path> --doctor-id <doctor-id> --operator-label <operator-label> --grant
python scripts/manage_budget_admin.py --db <business-db-path> --doctor-id <doctor-id> --operator-label <operator-label> --revoke
```

周期补偿入口（参数应与生效策略一致）：

```powershell
python -m martin.memory.governance_jobs --doctor-id <doctor-id> --thread-id <authorized-thread-id> --min-sources 12 --trigger-tokens 12000 --summary-tokens 2400 --max-jobs 4 --max-attempts 3
```

源码回退使用实施前快照逐文件审阅恢复，不能全工作区 reset。策略回退用版本 API 生成新版本；派生摘要可从有效原始来源重建。未知旧条目原数据仍保留；没有移除业务历史或改变事实确认方式。

## 12. 已知限制与后续

- 有限合成 P0 零违规不证明真实世界永远零风险；未进行真实 CT 推理、疾病判断或临床上线验收。
- 自动近重复只覆盖有限等价规则；未建立自由文本临床等价自动化或 Stable Lesion ID。
- 摘要为抽取式，溯源封装有额外空间；实际节省需按最终注入结构测量，不能用仅原文长度充当完整压缩率。
- P1 样本有限，真实模型一次配对不是整体时延、失败率或成本 SLA；tokenization framing 仍为估计。
- 单 worker 锁可能增加并发等待；后台需要周期补偿。多 worker、SQLite 争用、生产负载与 PostgreSQL 迁移留 V2.3。
- 测试使用 tmp 下全新 app/store/vector/checkpoint/knowledge/object 路径；没有读取或修改真实患者库，没有授予实际医生 capability。

## 13. 完成结论与最终 Git

V2.2 在执行方案的**合成记忆治理与单 worker工作站范围**完成：P0确定性硬约束无已知剩余违规、完整仓库收集回归通过且后续两个修复分别补影响面回归；P1有可重复基线与实际模型对比，资源退化与口径限制已明示；真实REST/WS/独立报告、公开答复、管理员与普通医生浏览器行为已验证。

最终分支和HEAD与基线相同，工作区仍包含V2.1、V2.2及实施前未知修改。已有用户计划文件哈希与实施前一致。源码/文档/前端/新增管理员CLI共221文件凭证模式扫描0命中，`.env`被忽略且未跟踪；验收快照/数据库/公开合成答复/截图在精确gitignore路径内；`git diff --check`通过。没有提交或推送，也没有对真实患者数据、部署环境或实际医生权限执行变更。

最后两个修复后的源码哈希、凭证扫描、人工复核分别为 `tmp/v22-final-privacy/final_source_manifest.json`、`source_scan.json`、`semantic_review.json`；完整回归和后续影响面源码时间点分别保存，便于审计重现。

交付索引：执行方案、baseline、本文、README/ROADMAP、核心模块、维护CLI、回归测试与三个V2.2验证脚本。完整证据保留在tmp供本地复查，未纳入Git。验收不等于真实CT、临床上线或多worker并发验收。
