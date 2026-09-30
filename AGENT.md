# Martin 项目协作规则

## 项目与职责

Martin 是面向临床医生的医学影像辅助系统。Agent 位于 martin/agent，视觉在 martin/vision，知识检索在 martin/rag，报告在 martin/llm，后端在 api，前端在 frontend。
修改前阅读相关实现、测试与文档；正确性优先，修复后再扩大范围。当前任务与验收以对应阶段执行文件为准；阶段状态不写入本文件。

## 环境与依赖

- 先检查 README.md、pyproject.toml、requirements.txt、前端 package.json/lock 和存在的正式环境文件。
- 项目要求 Python ≥3.10；README 的初始环境示例为3.10。其他版本须有兼容性依据，版本下限不等于全部组合均已验证。
- Conda 是推荐方式，不强制环境名；本地解释器路径不是项目规范。
- 原环境不存在时，可以按正式配置建立隔离环境。开始前说明版本与选择依据，记录解释器及实际依赖版本，不静默切换环境。
- 正式文件有差异时明确报告、区分可兼容约束和真实冲突。不能用旧执行记录替代依赖配置，也不能为通过测试擅自升级核心库。
- 测试优先使用 scripts/run_tests.ps1；解释器应可显式配置，或来自已选择并激活的项目环境。不得硬编码某台机器路径或在失败时静默回退。
- MinIO 使用可信来源、当前平台支持的程序；从仓库根目录运行，相对数据目录为 data/minio。不要使用已知不受支持的仓库内可执行文件。

### 本机实测环境事实（2026-09-30，Windows 开发机验证）

以下为实测踩过的坑，换机器时按此对照：

- **pytest 必须加 `--basetemp=<项目内目录>`**：本机 `%TEMP%\pytest-of-*` 权限损坏，否则批量出现 WinError 5 假 ERROR（不是代码问题）。
- **日志重定向直接用 `python -m pytest > f 2>&1`**：PowerShell 5.1 的 `Tee-Object` 会把日志写成 UTF-16 乱码。
- **git push / HuggingFace 直连可能被网络拒**：本机走代理 `127.0.0.1:7897`（`git -c http.proxy=... -c https.proxy=... push`）。环境变量里的另一个代理端口不通。
- **LLM 凭据不会被自动加载**：凭据放在 `<工作区根>/conda/envs/<env>/conda-meta/state`（`env_vars` 字段：DEEPSEEK_API_KEY / DEEPSEEK_BASE_URL / DEEPSEEK_MODEL）只是本机约定，conda 不读它；启动服务或跑验收脚本时需手动读出注入环境变量。凭据值永不入仓库。
- **前端构建用系统 Node 的 npm**：本机受管 Node 的 npm 有 MODULE_NOT_FOUND 问题；`cd frontend && npm run build` 后 dist 即生效（服务 StaticFiles 挂目录，无需重启）。
- **live 验收脚本**在 `validation_scripts/`（已入库），独立监听 8001 并自建隔离三库；证据产物落在仓库外 `../validation/`（git-ignored 级别的本机证据）。8000 常驻服务不是其必要条件。

## 子系统技能

涉及验证时先读 martin-quality-runtime，再读相应技能；跨模块读取多项。位置为 .agents/skills/<name>/SKILL.md。

| 修改范围 | 必读技能 |
|---|---|
| Agent、工具、Prompt、CaseContext、sessions、审计来源 | martin-agent-policy |
| 知识文档、Chroma、加载、检索和溯源 | martin-rag-knowledge |
| CT、MinIO、影像格式、MONAI | martin-vision-pipeline |
| FastAPI、Vue、REST/WebSocket、病例恢复 | martin-web-workstation |
| 报告生成、证据和模板 | martin-reporting |
| 测试、构建、配置、日志隐私 | martin-quality-runtime |

这些是开发流程，不是运行时临床插件。技能中的历史机器配置不能覆盖正式环境原则。

## 代码和架构

- 遵循现有模块边界及 pyproject 中格式配置：Black 行长88、isort black profile；不夹带无关格式重写。
- thread_id 是当前会话隔离边界；工具更新、Prompt 可见状态及持久化必须有明确协议。
- 持久化失败必须可检测并通过调用链报告，不能返回已保存的假成功。
- Prompt 是投影；checkpoint 保存运行状态，不等同长期业务数据库。规划中的数据库不能描述成已实现事实源。
- 接口或状态字段变化时检查 CLI、REST、WebSocket、前端和旧数据恢复契约。

## 验证与交付

- 区分“已修改、已静态检查、已运行、已测试、已通过”，只报告有证据的结论。
- 运行最小相关单测，再按风险验证真实持久化和跨层行为；前端变更需运行构建。
- 模拟测试不能替代真实 SQLite 恢复验证；模拟 CT 检测器不能冒充真实 MONAI 推理通过。
- 缺模型、数据、网络或密钥时显式记录未覆盖或跳过，不以无断言返回冒充通过。
- 记录主要命令、测试范围、失败类别、剩余阻塞和下一步；缺陷区分环境、原项目和当前修改。

## 安全与 Git

- 不泄漏密钥、患者信息、原始影像或不必要的用户文本，不记录完整思维链；医学来源必须有可追溯工具证据。
- 不提交运行数据库、模型、日志、审计记录、凭据和测试产物；夹具使用合成数据与临时目录。
- 修改前检查工作树，保留用户未提交工作；迁移先备份，不能以 reset --hard、clean 或强制覆盖消除未知修改。
- 提交前审查差异和相关验证，遵守任务的验收及提交范围。不要宣称未验证改动已完成。

