# Martin 长期记忆 V2 开发交接

更新日期：2026-10-10。开发分支：`codex/memory-v21-governance`。

## 1. 先读哪些文档

| 文档 | 用途 |
| --- | --- |
| [V2 原始可信治理方案](MARTIN_LONG_TERM_MEMORY_V2_TRUSTED_GOVERNANCE.md) | 用户提供的原始设计输入，原文归档；其中 Proposed、基线与阶段描述属于提出方案时的状态 |
| [V2 实施计划](MARTIN_MEMORY_V2_IMPLEMENTATION_PLAN.md) | 分批实施、事实与授权边界、V2.3 后续方向 |
| [V2.2 执行方案](MARTIN_MEMORY_V22_EXECUTION_PLAN.md) | 已确认的 D1–D8、P0/P1 硬约束，不重新讨论已确认决策 |
| [V2.1 验收](../refactor/MARTIN_MEMORY_V21_ACCEPTANCE.md) / [V2.2 验收](../refactor/MARTIN_MEMORY_V22_ACCEPTANCE.md) | 实际实现、命令、结果与未覆盖项 |
| [路线图](ROADMAP.md) / [开发规则](../../AGENT.md) | 当前待办和项目约束 |

原始设计方案不能代替当前源码和验收结果；历史交接文件中的旧分支、机器路径及启动状态不适用于本次接续。

## 2. 当前完成状态

### 已修改

- V2.1：来源、修订/撤回、未核实声明与 Finding 冲突、全路径注入资格判断及记忆管理界面。
- V2.2：风险分级去重、有源抽取摘要、后台治理队列、统一上下文预算、分阶段证据处理、预算策略版本/审计/回退与管理界面。
- 来源不明旧病例记忆保留原数据，但阻断普通 Prompt/摘要注入；新写入绑定医生。
- `budget_admin` 是现有医生身份上的独立能力，默认关闭，不增加患者访问权限。

### 已运行 / 已通过

- V2.1 相关回归 340 passed。V2.2 最后全量 587 collected、572 passed、15 skipped、0 failed。
- 全量之后的两个修复分别完成影响面回归：79 passed、114 passed；这些测试与全量有重叠，不能相加。
- 方舟真实模型 11 次成功调用、7 组 28 项检查通过，7 条公开回答已人工复核；包含 REST、WebSocket、独立报告与一次 P1 配对。
- 前端生产构建通过；前端行为检查 8/8、浏览器操作检查 9/9。
- 完整记录、P1 对照口径、资源变化和跳过原因见 V2.2 验收报告。

### 尚未验证

- 真实 CT/MONAI/MinIO 全链路、临床知识语料与临床有效性。
- Stable Lesion ID、生产负载、多 worker/跨进程 SQLite 并发与性能 SLA。
- 新电脑的环境与运行结果需要接手后实际验证；旧电脑的测试结果不表示新电脑已通过。

## 3. 换电脑拉取

新目录：

```bash
git clone --branch codex/memory-v21-governance https://github.com/freshmanXzz/medical_ai_agent.git
cd medical_ai_agent
git log -3 --oneline
git status --short
```

已有克隆先检查并保留本地修改，再执行：

```bash
git fetch origin
git switch codex/memory-v21-governance
git pull --ff-only
```

本次提交推送的目标是上述开发分支；接续时明确选该分支。查看远端 `origin/codex/memory-v21-governance` 与本地 HEAD 是否一致。

## 4. 重建环境与验证

按 [README 快速开始](../../README.md) 和正式依赖文件选择 Python ≥3.10 的兼容环境；当前验收使用 Python 3.10.19。不要复制旧机器解释器路径或无声升级核心依赖。

- 后端：安装 `requirements.txt`，再 `python -m pip install -e .`。
- 前端：在 `frontend` 运行 `npm ci`、`npm run build`，使用仓库锁文件。
- 在新机器本地环境或 git-ignored `.env` 配置 `DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL`。当前服务为火山方舟 Coding Plan，地址与模型示例见 README；密钥自行配置。
- BGE、MONAI 权重、MinIO 程序按 README 重新准备；模型和本机程序不在 Git 中。
- 新建隔离开发库时，先设置自己的合成种子账号密码，再按 README 执行 `scripts.init_app_db` / `scripts.seed_entity_v0`。已有运行数据库先备份并检查，不能当作空库覆盖。

Windows 激活所选项目 Conda/venv 环境后，在仓库根运行：

```powershell
./scripts/run_tests.ps1 -PytestArgs @('tests', '-q', '--basetemp=./.pytest_tmp')
python validation_scripts/memory_v22_governance_metrics.py
```

包装器使用已激活环境或显式 `MARTIN_TEST_PYTHON`，不会回退系统 Python。完整测试中缺资产/外部服务的项目应明确 skip，不能把 skip 记成通过。

真实模型复跑（会调用当前配置的模型服务，仅使用隔离合成数据）：

```powershell
python validation_scripts/memory_v22_live_acceptance.py
python validation_scripts/memory_v22_live_acceptance.py --report-source-only
```

检查结构化 checks 后，继续复核最终公开回答。`REVIEW` 不代表人工复核已完成。脚本的隔离数据库、模型输入与公开回答在本地忽略目录生成，不进入 Git。

`memory_v22_quality_baseline.py` 的历史 V2.1 比较依赖实施前本地源码快照；快照未入 Git，新克隆不能直接复跑该历史对比。该对比结论与口径在验收报告中保留。另两份 V2.2 脚本不依赖这份历史快照，可用于新机器当前实现验收。

## 5. 提交范围与本地资产

本次发布整合已有 V2.1 与本轮 V2.2 的源码、测试、维护命令、验收脚本和方案/验收/交接文档。实施验收报告中的“未提交、未推送”是授权发布前的历史状态，当前状态由 Git 记录确认。

`.env`、运行数据库、向量库、模型、上传对象、日志、完整临时证据和构建缓存不上传。验收报告中的 `tmp/...` 是原机器的本地证据索引；在新电脑按入库脚本重建，不代表这些文件随克隆到达。

本机已有的根目录 `MARTIN_LONG_TERM_MEMORY_PLAN.md` 表格格式修改、前端 `tsconfig.tsbuildinfo` 缓存，以及来源不属于本阶段的教程、履历脚本、资料、`data/output/tmp` 与本机可执行文件保留在原工作区，没有混入本次发布。

## 6. 下一步与协作模式

- 已确认的 V2.3 方向：先测检索质量、无关注入、来源覆盖、冲突发现、错误作用域/失效条目泄漏、超时降级、延迟和 SQLite 多进程争用；性能阈值先有基线，再定目标。
- PostgreSQL 迁移由可复现的争用/部署证据决定；稳定病灶 ID 属于独立业务设计。
- 真实 CT、知识库实测和其它业务待办按 ROADMAP 单独验收。本次发布不自动启动下一阶段。
- **当前协作模式**：延续用户本次明确授权——具体技术实现可自主判断；重要架构冲突、医疗事实边界或业务取舍先给方案并与用户讨论；D1–D8 及已确认的旧记忆隔离、管理员能力方案不重新讨论。
- **本机瞬时状态**：只记录在 git-ignored `LOCAL_NOTES.md`；新机器按实测建立自己的记录。
