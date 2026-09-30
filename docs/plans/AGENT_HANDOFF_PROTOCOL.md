# Agent 交替工作交接协议

日期：2026-09-30。适用对象：Kai（WorkBuddy 端）与另一个实施 agent 交替开发 `medical_ai_agent`。目标：任一方接手时，**30 分钟内**从冷启动恢复到可继续开发的状态。

---

## 一、已审查：另一个 agent 目前留下的资产

| 资产 | 位置 | 评价 |
| --- | --- | --- |
| 验收文档（四段式：已修改/已运行/已通过/尚未验证） | `docs/refactor/*.md` 6 份 | ✅ 好，接手最快的信息源 |
| 批次进度日志 | `docs/plans/REFACTOR_PROGRESS.md` | ✅ 好，权威副本已入库 |
| 执行计划 / ADR / 字段映射 | `docs/plans/` + `docs/refactor/` | ✅ 好 |
| 可复跑的 live 验收脚本 | `D:/agent_martin/validation/*.py` | ⚠️ **在仓库外，不进 git——换机器即丢失** |
| live 证据（evidence.json + 隔离三库 + audit） | `validation/store-v1-live-*/` | ⚠️ 本地证据可接受，但文档引用的是绝对路径，换机器后断链 |
| 服务运行产物（pid/log） | `validation/martin-service-*.pid/.log` | ⚠️ 有记录但**没写服务是否该常开**，接手方跑 live 时曾因 8000 无服务而崩 |
| LLM 凭据 | `conda/envs/medical_ai_agent/conda-meta/state` | ❌ 非标准私有位置，只有写脚本的人知道；换机器不可迁移，也不该迁移 |
| 批次前代码备份 | `backups/` | ✅ 好（本地保险） |
| 环境坑（--basetemp / 7897 代理 / Tee-Object 乱码） | 散落在各验收文档 | ⚠️ 分散，无单一权威清单 |

## 二、每次交班必须留下的东西（实施 agent 的义务）

按此清单逐项核对，缺一项视为**未完成交班**：

### 1. 工作树状态：三选一并写明

- **A（首选）**：验收通过的工作全部提交并推送，commit message 写明批次/场景与验收结论；
- **B**：进行中的工作提交为 WIP commit（`wip:` 前缀），message 写清"改到哪、差什么、下一步"；
- **C**：实在不能提交（如改动会破坏他人基线），在 `docs/plans/REFACTOR_PROGRESS.md` 追加一节"交班时的未提交改动"，列出文件清单与每个文件的意图。

> 禁止：留一堆未提交修改且无任何说明。接手方无法区分"进行中"与"已完成待提交"。

### 2. 验收脚本必须入仓库

- 所有可复跑的验收/探针脚本放 `medical_ai_agent/validation_scripts/`（入库），不再放仓库外；
- 脚本头部 docstring 写明：判定标准、隔离方式（独立库/端口）、如何复跑；
- 脚本不得含任何密钥（从环境变量或 `conda-meta/state` 读，脚本里只写读取位置）。

### 3. 文档四段式收尾

每个场景/批次结束，在 `docs/refactor/` 对应文档写全四段：**已修改 / 已运行 / 已通过 / 尚未验证**。"尚未验证"一栏禁止省略——没有它，接手方会把未验证的东西当结论用。

### 4. 服务与环境状态声明

交班时在 `REFACTOR_PROGRESS.md` 追加一个固定格式小块：

```text
## 交班状态（YYYY-MM-DD HH:MM）
- 8000 服务：运行中/已停止（pid 文件：...）
- data/ 三库：是否为合成种子，有无生产数据
- 工作树：干净 / 未提交（见第 X 节）
- 阻塞项：无 / ...
```

### 5. 环境事实只写一处：`AGENT.md`

新增环境坑（代理端口、临时目录权限、编码问题、模型资产位置）统一补进仓库内 `AGENT.md` 的环境小节，不在各验收文档里重复。验收文档引用 `AGENT.md` 即可。

### 6. 凭据：只声明位置，不写值

- 任何文档、commit、脚本中**不得出现密钥明文**；
- 交班块里写"凭据在 `conda-meta/state`（本机）"或"已转入 `.env`（git-ignored）"即可；
- 换机器由 Martin 亲自重新配置。

## 三、接手方的开场 checklist（对等义务）

接手方按顺序执行，全部通过才算完成接管：

| # | 动作 | 通过标准 |
| --- | --- | --- |
| 1 | `git log --oneline -5` + `git status` | 与交班块声明一致 |
| 2 | 读 `REFACTOR_PROGRESS.md` 最新两节 | 知道当前批次与阻塞项 |
| 3 | 读 `docs/refactor/` 本阶段验收文档 | 区分"已通过"与"尚未验证" |
| 4 | 跑阶段专项测试（带 `--basetemp`） | 与交班记录的通过数一致 |
| 5 | 需要跑 live 时先确认凭据可读、服务状态 | 不复现"8000 无服务"事故 |

## 四、项目迁移到另一台电脑：操作指南

**结论：GitHub 只覆盖 60% 左右，不够。** 分三类处理：

### A. GitHub 上传即可（已覆盖）

代码、测试、`docs/`（计划/验收/ADR/映射）、`scripts/`、`requirements.txt`——都在 `refactor/memory-auth-v1` 分支。迁移前**必须先提交推送当前工作树**（现在还攒着 V1 修复 + 口径收紧 + 文档未提交）。

### B. GitHub 放不进去、需单独处理的资产

| 资产 | 大小/性质 | 迁移方式 |
| --- | --- | --- |
| `models/embedding/bge-small-zh-v1.5` | git-ignored 模型 | 移动硬盘/U 盘拷贝，或新机器走 `HF_ENDPOINT` 镜像重新下载 |
| LLM 凭据（ark API key） | 密钥，禁止入库 | 你亲自在新机器配置：`conda-meta/state` 或 `.env`（记得 `DEEPSEEK_BASE_URL` 是火山引擎地址，不是官方 DeepSeek） |
| `validation/*.py` 验收脚本 | 仓库外 | **迁移前先按第二节第 2 条搬入仓库**，否则丢失 |
| `validation/store-v1-live-*/` 证据 | 本地证据 | 可不迁移；文档结论已在 `docs/` 内，需要时重跑脚本再生成 |
| `data/*.sqlite` | 合成种子库 | **不用迁移**，新机器跑 `python -m scripts.init_app_db && python -m scripts.seed_entity_v0` 重建 |
| MONAI 权重 `model.pt` | 一直缺失 | 哪台机器有就放哪台，或提前下载 |

### C. 新机器环境重建步骤

```bash
# 1. 克隆
git clone -b refactor/memory-auth-v1 https://github.com/freshmanXzz/medical_ai_agent.git
cd medical_ai_agent

# 2. 建环境（按 README/requirements.txt，不要照抄旧机器的 conda 路径）
conda create -n medical_ai_agent python=3.10
conda activate medical_ai_agent
pip install -r requirements.txt
pip install -e .   # schema.sql 打包需要

# 3. 配凭据（你亲自做）
#    方式一：conda-meta/state（与验收脚本兼容）
#    方式二：环境变量 DEEPSEEK_API_KEY / DEEPSEEK_BASE_URL / DEEPSEEK_MODEL

# 4. 重建业务库 + 种子
python -m scripts.init_app_db
python -m scripts.seed_entity_v0

# 5. 验证
python -m pytest tests/ -q --basetemp=<项目内目录>
```

### 迁移前置检查单（离开旧机器前）

- [ ] 当前工作树已提交并推送（含 V1 修复、口径收紧、验收文档）
- [ ] `validation/*.py` 四个脚本已搬入仓库并推送
- [ ] `AGENT.md` 环境小节已更新（7897 代理、--basetemp、凭据位置）
- [ ] 确认 `git ls-remote` 远端 HEAD = 本地 HEAD
- [ ] BGE 模型已拷贝或确认新机器可下载
- [ ] 密钥已准备好在新机器配置（不从 git 走）

---

*本协议为双向约束：交班方按第二节留痕，接手方按第三节核收。任何一方发现协议本身有缺口，直接修改本文件并在进度日志注明。*
