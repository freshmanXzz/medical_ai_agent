# 重构执行记录

## 2026-09-28

- 已读取重构计划、仓库 AGENTS.md 和质量、Agent、Web 技能。
- Git HTTPS helper 已定位；两次联网克隆分别因连接重置和连接失败终止。
- 已从 GitHub 官方 codeload 下载 main 分支源码归档，原始归档保留在 `medical_ai_agent-main.zip`。
- 工作源码位于 `source/medical_ai_agent-main`。这是源码归档，不是 Git checkout；尚未建立重构分支或提交。
- 本机未找到计划中的 Python/Conda 命令；发现内置 Python 3.12.14，但项目明确禁止未经用户同意更换测试环境。已向用户请求环境选择，尚未执行 Python 验证或安装依赖。

## 已写入但尚未验证的 Phase 1 改动

- 动态 Prompt 使用工具当前操作的 CaseContext；不再用 Graph 输入快照覆盖工具更新。
- 完成调用后仍由 save_case_context 统一写入快照。
- 结果解析只处理最后一条 HumanMessage 后的调用，并按 tool_call_id 匹配结果。
- 保存失败抛出 CasePersistenceError；REST 与 WebSocket 对话路径返回保存失败提示。
- 新增四个回归测试，覆盖历史调用过滤、乱序工具结果、状态覆盖和持久化异常。

## 尚未完成

- 恢复正常 Git checkout，建立 refactor/memory-auth-v1 分支。
- 原项目 baseline、依赖安装、前后端启动及所有回归验证。
- 真实 LangGraph/SQLite 重启恢复、同轮 Prompt、CT 工具、API 失败路径的集成测试。
- 原代码尚无 report_draft 字段，需要增加字段与报告保存协议并补测试。
- 运行对象与中间 checkpoint 的一致性、失败恢复及并发问题仍待验证和完善。
- Phase 1 尚未通过验收；Phase 2–13 未开始。

不能将本记录中的代码改动视为测试通过或整个重构完成。

## 2026-09-28 — 按当前 AGENT.md 恢复正式工作区

### 已完成
- 已阅读工作区新增的 AGENT.md，范围限定为 Phase 0 / Phase 1。
- Git 重试成功：正式仓库为 `medical_ai_agent`，基线提交 `5851e91`。
- 已建立 `refactor/memory-auth-v1` 分支。
- 四个修改文件已备份至 `backups/phase1-before-migration`，归档源码保持不变。
- 已比对 ZIP 原始文件与 checkout 中两个待覆盖的既有文件，内容一致后迁移了四个修改文件。
- 后续工作以正式仓库为准，先前记录中的“未建立 Git checkout”状态已解除。
- 按最新 AGENT.md，report_draft 和并发问题不属于本轮验收范围，撤销此前将其列为待实现项的安排。

### 执行命令
```text
git -c http.version=HTTP/1.1 clone https://github.com/freshmanXzz/medical_ai_agent.git medical_ai_agent
git switch -c refactor/memory-auth-v1
git diff --check
git diff --stat
git status --short --branch
```

### 验证结果
- Passed: 原始文件基线比对；git diff --check（仅文本差异检查，不是 Python 验证）。
- Failed: 无已运行的 Python 测试，因此没有测试失败结论。
- Skipped: Python 测试、LangGraph/SQLite、后端启动、前端启动、LLM、MONAI 均未验证。

### 发现的问题
- README 推荐 Conda + Python 3.10；pyproject 声明 Python >=3.10。
- 测试包装器默认指定的旧 Conda Python 路径不存在。
- PATH 和已检查的常见目录中未发现 Conda 环境；不能据此断言所有磁盘均无环境。
- 依赖文件使用版本下限，没有提供精确的原环境锁定信息。

### 当前阻塞
- Python / Conda 环境尚未明确。未使用内置 Python 3.12 替代原测试环境。

### 下一步
- 确认用户提供的现有 Conda 环境，或获准按 README 创建 Python 3.10 Conda 环境。
- 恢复依赖、记录 baseline，再运行最小回归测试与真实 LangGraph/SQLite/API 集成测试。
- Phase 1 仍未完成，未提交、未推送，未开始 Phase 2。

## 2026-09-28 — 规则协调草案

### 已完成
- 完整比较工作区 AGENT.md、正式仓库 AGENTS.md、ZIP副本，并核对README、Python/前端配置、测试脚本与环境残留。
- 生成正式仓库内 AGENT_RECONCILIATION_REPORT.md、AGENT.proposed.md、docs/refactor/PHASE1_EXECUTION.proposed.md。
- 证据支持 Python >=3.10；README推荐Conda并示例3.10/martin，不支持将monai_learning或旧E盘路径当跨机器强制规范。
- 发现测试脚本、视觉技能与演示文档仍含本地环境限制，正式替换时需同步处理。

### 验证结果
- Passed: git diff --check；原仓库规则、测试脚本、视觉技能没有新增差异。
- Failed: 无运行测试结论。
- Skipped: 环境安装、Python/集成测试与服务启动；草案未生效。

### 当前阻塞与下一步
- 用户协调文件第17节明确要求草案输出后等待确认，未覆盖或删除原规则，未提交。
- 确认后协调正式主规则、AGENTS入口及工作区旧入口，修测试脚本与技能环境残留，然后依据README的3.10方案继续Phase0/1。

## 2026-09-28 — 应用已批准规则，恢复环境

### 已修改
- 主规则已落为 medical_ai_agent/AGENT.md；Phase1执行文件已正式落地，协调报告保留。
- 仓库AGENTS.md和工作区AGENT.md改为指引入口；测试脚本支持显式解释器/已激活环境，不再回退旧机器路径。
- 原规则、脚本、技能和四个未提交Phase1文件备份于 backups/rules-approved-20260928-103922；原草案仍保留。
- 视觉技能环境引用已协调；新增真实LangGraph/SQLite集成测试（尚未运行）。

### 已运行
- 官方Miniforge下载及签名检查：Valid，NumFOCUS；静默安装到工作区，不注册系统Python或修改PATH，退出码0。
- conda create --name medical_ai_agent python=3.10 pip --yes --override-channels --channel conda-forge：退出码0。
- 实际解释器：D:\agent_martin\conda\envs\medical_ai_agent\python.exe；Python 3.10.21，SQLite 3.53.4。
- 使用固定核心版本约束对 requirements.txt 与项目元数据联合 dry-run，报告在 validation/dependency-resolution.json，日志在 validation/dependency-resolution.log。

### 环境决策
- 无原环境锁文件，不能声称还原旧电脑精确依赖版本。
- 初始固定torch2.0.0、torchvision0.15.1、torchaudio2.0.1、MONAI1.3.0；CPU轮子用于状态验证，不声明GPU可用。
- 固定LangChain1.3.0、core1.4.0。包元数据要求LangGraph>=1.2，因此选1.2.0；它要求checkpoint>=4.1，因此选4.1.0和兼容的sqlite saver3.1.1。均满足正式声明，不修改声明以绕过解析。
- numpy1.26.4和transformers4.41.2/sentence-transformers2.7.0用于保持torch2.0兼容；未升级已安装核心库。

### 尚未验证
- 核心依赖安装及pip check；原基线、单元、集成、API和服务启动测试仍待运行。

## 2026-09-28 — 环境恢复与首次运行完成，按用户要求停止

### 已修改
- 已批准的规则及环境测试入口已落地，原文件和Phase1代码均有备份。
- 新增状态回归/真实LangGraph集成测试；修正旧测试夹具call_1与1不匹配的问题。
- 用户随后要求不再改动，配好基础环境和依赖、跑通一次即停止；之后仅补本执行记录。

### 已运行
- Conda环境：medical_ai_agent。
- Python实际路径：D:\agent_martin\conda\envs\medical_ai_agent\python.exe。
- Python 3.10.21；SQLite 3.53.4；未使用系统Python3.12。
- 实际核心包：torch2.0.0+cpu、torchvision0.15.1+cpu、torchaudio2.0.1+cpu、MONAI1.3.0、numpy1.26.4、LangChain1.3.0、langchain-core1.4.0、LangGraph1.2.0、checkpoint4.1.0、sqlite saver3.1.1、FastAPI0.141.1。
- 官方文件下载慢，镜像安装保留固定版本及官方SHA256；两个非核心包的缺失哈希已从官方PyPI补齐。
- 依赖安装进程明确返回0后，pip check再次执行：No broken requirements found。
- README/pyproject/requirements存在声明范围及下限差异，联合解析成功；未修改正式依赖声明，也未为通过测试升级固定核心包。
- 前端npm ci及npm run build退出0。Node24.19.0/npm11.17.0，前端版本遵守原lock。
- 实际启动uvicorn，GET /api/health返回200及status=ok；GET /返回200并由FastAPI提供已构建前端。验证结束已关闭本次服务。

### 已测试 / 已通过
- 原基线5851e91最小单元：27 passed。
- 修改版首轮：26 passed、1 failed，失败为旧夹具tool_call_id错配。
- 修正夹具并加入错配拒绝测试后：32 passed。
- 新LangGraph/SQLite/API集成：7 passed。覆盖SQLite重开恢复及继续对话、会话隔离、实际同轮Prompt、CT有结节/无结节持久化、REST/WS的graph/final_save写失败路径。
- 既有会话/API回归：31 passed、1 failed。原基线复现同一失败：无DEEPSEEK_API_KEY时，影像接口在检查空影像来源前创建模型，导致旧测试失败。未继续扩展修复。
- torch及monai实际import成功；CUDA不可用（本次CPU验证环境）。

### 尚未验证 / 新阻塞
- 未配置真实LLM key；未调用外部模型，真实聊天尚未验证。
- 未找到视觉/嵌入模型权重，真实MONAI推理、知识库检索及MinIO上传链路未验证。
- 模拟检测器与脚本模型的测试通过不代表真实医学推理通过。
- HuggingFace默认缓存目录出现写权限提示；本轮未下载模型，未改系统缓存配置。
- 存在原项目测试依赖真实key的问题及已有弃用/前端包体积警告。

### 证据
- validation/environment.json、installed-freeze.txt、constraints-py310.txt、resolved-py310-mirror.txt。
- validation/dependency-resolution.json、dependency-install-final.log、pip-check.log。
- validation/baseline-unit.log、phase1-unit-first.log、phase1-unit-final.log、phase1-integration-first.log。
- validation/phase1-existing-integration.log、baseline-api-missing-key.log。
- validation/frontend-build.log、backend-health.json、backend-stdout.log、backend-stderr.log。

### 停止状态
- 基础环境、依赖和一次实际HTTP启动验证完成。
- 按用户最新要求停止，不继续修代码、不运行更多测试、不开始Phase2、不提交或推送。
- 不声明Phase1全部完成。

## 2026-09-28 — Entity V0 Batch 0：停止于测试门槛

### 已修改
- 简审 `D:\mutil-AGENT_CHAT\MARTIN_ENTITY_V0_EXECUTION_PLAN.md`，对照当前 AGENT.md、Phase1 执行文件和未提交工作树。
- 旧重构计划先备份至 `backups/MEDICAL_AI_AGENT_REFACTOR_PLAN.before-entity-v0.md`，原文保留，仅添加 2026-09-28 Architecture Override 和相关 SUPERSEDED 标记。
- 正式仓库新增 `docs/refactor/ADR-001-entity-store-boundary.md`：app.sqlite=业务事实/实体/授权、SqliteStore=跨 Thread Agent 记忆、SqliteSaver=Thread/checkpoint 状态；不建 app.sqlite.memories；V1 threads.id=LangGraph thread_id。
- 现有测试包装器已经支持 MARTIN_TEST_PYTHON 和 pytest 参数；本批未改脚本及 Phase1 业务代码。

### 已运行 / 已测试
- `git diff --check`：通过（Git 输出了既有换行转换提示）。
- 当前工作树通过 `scripts/run_tests.ps1 --maxfail=1 -q` 启动完整测试集合，首个失败为 `tests/test_agent_pipeline.py::TestAgentInitialization::test_create_agent_with_default_tools`；结果 1 passed、1 failed 后按设置停止，未称为全量通过。
- 错因：本机无 DEEPSEEK_API_KEY，该旧测试直接创建真实 Agent 模型。
- 在原始提交 5851e91 的独立基线目录运行同一测试，得到相同 ValueError/失败，证明本失败为已有测试的环境依赖，并非本次文档变更造成。
- 先前 Phase1 最小单元32 passed、真实 LangGraph/SQLite/API 集成7 passed；既有会话/API测试31 passed、1 failed，另一个缺少模型配置问题也在基线复现。Phase1 完整验收仍未完成。

### 停止原因与剩余工作
- 新 Entity V0 计划第6节规定“当前批未通过，禁止进入下一批”，第10节规定批次测试失败须停止并报告差异；正式 Phase1 执行文件亦要求验收通过前不进入业务数据库。
- 因此 Batch 1 的 app.sqlite/十张表、Auth 与后续 Store 均未开始；未提交或推送，原 Phase1 未提交修改保留。
- 下一步需要决定如何处理旧测试的外部模型配置依赖并完成 Phase1 基线验收，然后才能重跑 Batch0并按批次继续。

## 2026-09-28 — Entity V0 Batch 0：旧密钥依赖修复后的验证

### 已修改
- 用户提供模型密钥并允许继续；密钥未写入仓库、环境文件或日志，也未在本轮调用外部模型。
- `tests/test_agent_pipeline.py` 两项仅验证 Agent 装配/工具注册的旧测试改为模拟模型和 LangChain 工厂，解除无关的真实 API Key 依赖；Phase 1 业务代码未改。

### 已运行 / 已测试 / 已通过
- 指定 Conda Python 3.10 环境运行 `tests/test_agent_pipeline.py -q --maxfail=1`：10 passed。
- `git diff --check`：通过（仅有既有文件换行转换提示）。

### 失败 / 尚未验证
- 全量测试启动后在约 40% 处出现测试错误，已中止扩展；随后用 `-q -x --tb=short` 定位首个错误：57 passed、1 error。
- 首个错误为 `tests/test_integration.py::TestIntegration::test_01_knowledge_base_loaded` 的 setup：本地缺 `BAAI/bge-small-zh-v1.5` embedding 模型，代码尝试从 Hugging Face 下载，但当前网络连接被系统拒绝（WinError 10013）。这项 RAG 集成测试依赖模型文件，不能以模拟通过代替真实通过。
- 首次非 `-x` 运行还显示后续错误/失败，但在测试中止前没有完整 traceback，不列为已定位结论。完整测试、真实 LLM、真实 RAG/MONAI 和 Phase 1 全部验收仍未完成；未进入 Entity V0 Batch 1。
- 新日志：`validation/entity-v0-batch0-full-suite-after-fixture-fix.log`。用户密钥未出现在日志中。

### 停止原因
- Entity V0 执行计划第 10 节要求批次测试失败时停止、记录并等待决策。当前阻塞由缺失的外部 embedding 模型与受限网络造成，API Key 不能解决该错误。

## 2026-09-28 — Entity V0 Batch 1 已验收

### 基线依据
- 用户提供 `MARTIN_PRE_REFACTOR_VALIDATION_HANDOFF.md` 并明确要求从 Batch 1 开始。独立验证记录 Phase 1 Core 35 passed / 0 failed；全量 170 passed / 1 failed / 5 errors / 2 skipped，未通过 6 项均为缺 BGE 模型的环境依赖。按该交接结论进入 Entity V0。

### 已修改
- 新增 `martin/db/schema.sql` 十张表、`app_db.py` 连接/初始化/事务管理与 `martin/db/__init__.py`；每个连接启用外键。
- 新增初始化与合成数据种子脚本，固定测试 ID D001/D002/P001/P002/C001/C002/C003；密码用 Argon2id 哈希，脚本从环境变量读取示例密码，不保存明文。
- 正式依赖中声明 `argon2-cffi`，wheel 包含 `schema.sql`；`.gitignore` 排除业务数据库及 pytest 临时目录。
- 新增 Batch 1 的 schema/seed 测试。

### 已运行 / 已测试 / 已通过
- Batch 1 专项测试：10 passed（含十表、索引、外键、CHECK、seed 权限矩阵、重复 seed、事务回滚）。
- `python -m scripts.init_app_db` 对正式 `data/app.sqlite` 连续运行两次成功；`python -m scripts.seed_entity_v0` 连续运行两次成功。直接 `python scripts/init_app_db.py` 因源码仓库未安装为包而失败，已采用模块调用方式并写入脚本文档字符串。
- 实库复核：10 表、foreign_keys=1、users=2、patients=2、cases=3、doctor_patient_access=2；无 memories 表。
- `pip check` 无依赖冲突；本地 wheel 构建成功且包含 `martin/db/schema.sql`；`git diff --check` 通过。

### 尚未验证
- Auth、授权、Repository、Agent 接线和 Store 均属后续批次；BGE 与 MONAI 模型资产仍未恢复。业务库是本地合成种子，不含真实患者数据。

## 2026-09-28 — Entity V0 Batch 2 已验收

### 已修改
- 新增纯 SQL Repository：User、AuthSession、Patient、Case、Thread、Access、Attachment、Finding、Report、Audit；由调用方传入连接并控制事务，不在 Repository 内做授权。
- 新增 Repository CRUD 与外键/版本规则测试；不触碰 Phase 1 Agent 状态代码。

### 已运行 / 已测试 / 已通过
- `tests/entity/test_repositories.py tests/entity/test_cascade_rules.py`：7 passed，覆盖 UUID、CRUD、回滚、Patient/Case 删除限制、授权关系撤销、Attachment 删除后 Finding 来源置空、Report 版本唯一。

### 尚未验证
- API Auth、服务层授权和 checkpoint 联动尚未接线；BGE/MONAI 外部资产依旧缺失。

## 2026-09-28 — Entity V0 Batch 3 已验收

### 已修改
- Argon2id 密码校验、服务端 opaque Session（Cookie 只保存原 token，app.sqlite 只保存 SHA-256 hash），HttpOnly/SameSite=Lax，生产环境强制 Secure。
- 新增登录/登出/当前医生与创建 Thread API；Thread ID 由服务端 UUID 生成，创建前查 Case 的 doctor_patient_access。
- REST/WS Agent 入口先核验 Cookie 与已有 Thread 的医生归属；CORS 允许限定来源携带 Cookie。相关旧 Phase 1/API 测试已更新为先登录并创建合法 Thread。

### 已运行 / 已测试 / 已通过
- `tests/auth tests/access/test_thread_authorization.py`：11 passed，含任意 WebSocket Thread 拒绝。
- Phase 1 Core 四文件回归：35 passed；持久化失败仍返回非成功，WebSocket 无成功 final。
- `tests/test_web_api.py`：13 passed；其中旧影像测试需要仅用于构造模型的本地占位 API Key，未调用外部 LLM。无占位时该旧测试仍触发已知初始化错误。

### 尚未验证
- Patient/Case/Thread 读取与其他会话/影像接口的统一授权属于 Batch 4；完整回归仍受 BGE 模型资产限制。

## 2026-09-28 — Entity V0 Batch 4 已验收

### 已修改
- AccessService/CaseService/ThreadService 的 Patient、Case、Thread 读取均要求 doctor_id；Thread 同时核验 owner 与关联患者授权；`read_only` 可读不可创建或写入 Thread。
- 新增 Patient/Case/Thread 的授权读取 API；旧会话列表、会话详情、CT 上传/分析与阅片路由也在读写前验证服务端身份及 Thread 授权，撤销访问立即生效。
- 旧 Web/阅片测试按合法登录和 Thread 调整，不改变 Phase 1 状态修复。

### 已运行 / 已测试 / 已通过
- `tests/access`：11 passed，含 D002 改 URL 读取 C001 拒绝、撤销访问后 Agent/会话/影像拒绝、会话列表过滤他人 Thread。
- `tests/test_web_api.py tests/test_ct_viewer.py`：21 passed（影像旧测试使用无网络占位模型配置）。

### 尚未验证
- Batch 5 事实链与字段映射、Batch 6 checkpoint 生命周期和完整回归仍待实施；外部 BGE/MONAI 资产缺失不变。
