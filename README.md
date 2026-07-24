# Martin — AI Medical Imaging Copilot for Clinicians

> 面向临床医生的 AI 医学影像辅助分析智能体：MONAI 影像检测 + RAG 知识增强 + LangChain Agent 编排 + DeepSeek 推理

Martin 是一个开源的医学影像 AI Copilot，面向**呼吸科 / 胸外科 / 影像科医生**，以肺结节检测为切入点，实现从**影像感知 → 知识检索 → 智能推理 → 报告生成**的完整辅助分析流程。

**核心定位：** 不是面向患者的医疗聊天机器人，而是医生工作流的 AI 影像辅助分析智能体。

---

## ✨ Features

- 👁 **3D 肺结节检测** — 基于 MONAI RetinaNet，支持 NIfTI / MetaImage 格式
- 🔍 **RAG 循证诊断** — ChromaDB + BGE 本地向量库，引用 Lung-RADS 等权威指南
- 🤖 **Agent 智能编排** — LangChain 1.x + LangGraph，多工具自主规划与调用
- 🧠 **会话级病例上下文** — `CaseContext` 按 `thread_id` 持久化患者信息、影像、结节、知识摘要与临床备注
- 📄 **多类型报告生成** — brief / detailed / research 三档，LCEL 声明式编排
- 💾 **会话与病例恢复** — 官方 `SqliteSaver` 保存历史会话；Web“病例记录”可恢复原会话并继续分析、生成报告
- 🌐 **临床影像工作站** — Vue 3 + FastAPI 三栏工作区（检查与发现 / 影像分析区 / 诊断信息链），Martin 作为可收起 Copilot
- 📎 **CT 上传与分析** — 左侧检查栏提供主上传入口；Copilot 中保留附件上传作为补充入口
- ⚡ **WebSocket 实时过程** — AgentTimeline 展示工具调用、观察结果、推理状态
- 🗄 **MinIO 对象存储** — 医学影像文件统一存储，CaseContext 关联 file_id
- 📚 **知识库原文查看** — 知识摘要以引用条目展示，点击"查看原文"弹出 Drawer 阅读完整指南文档
- 📝 **医疗审计溯源** — reasoning 字段 + JSONL 审计日志，全程可追溯
- 🖥 **GPU 加速推理** — CUDA 加速，支持本地模型部署

---

## 🏗 Architecture

```mermaid
flowchart LR
    User[用户输入] --> Agent[Agent Core]

    subgraph Agent[Agent Core]
        direction TB
        LLM[DeepSeek LLM]
        Planner[Planning / Reasoning]
        Memory[Memory System]
        LLM --> Planner
        Memory -.-> LLM
    end

    subgraph Tools[Core Tools]
        direction TB
        T1[analyze_image]
        T2[retrieve_knowledge]
        T3[generate_report]
        T4[update_case_context]
    end

    subgraph Knowledge[Knowledge / Models]
        direction TB
        Vision[MONAI RetinaNet]
        RAG[ChromaDB + BGE]
        Case[CaseContext]
    end

    Agent --> Tools
    Tools --> Knowledge
    Knowledge --> Agent

    Agent --> Output[最终响应]
```

**两层记忆架构：**

| 层级 | 实现 | 作用 |
|------|------|------|
| 对话记忆 | LangGraph `SqliteSaver` | 保存完整消息历史与 LangGraph checkpoint，支持重启恢复 |
| 病例记忆 | `CaseContext`（同一 checkpoint 的结构化状态） | 患者信息 / 影像 / 结节 / 知识摘要 / 临床备注 / 检测完成状态 |

**Web 工作站信息架构：**

| 区域 | 内容 | 作用 |
|------|------|------|
| 左栏：检查与发现 | CT 上传、文件状态、唯一的结节逐项清单 | 建立检查并选择待复核结节 |
| 中栏：影像分析区 | 深色分析画布、分析状态、当前选中结节 | 呈现 AI 的结构化分析结果；当前不是 DICOM/CT 切片阅片器 |
| 右栏：诊断信息链 | 结节尺寸与置信度、病例信息、RAG 引用、报告入口 | 将检测依据、医学知识和下一步操作放在同一审阅链中 |
| Martin Copilot | 可收起的对话与工具时间线面板 | 保留多轮问答、附件、WebSocket 过程展示，不占据主工作区 |

知识摘要支持“查看原文”：点击引用条目弹出 Drawer 展示知识库 Markdown 原文档（接口：`GET /api/knowledge/document/{filename}`）。

---

## 🔄 Workflow

```
用户输入
  ↓
AgentExecutor.invoke()
  ├─ 注入结构化病例上下文 (CaseContext)
  └─ LangGraph 循环：
       1. LLM 推理 → 是否调用工具
       2. 有 tool_calls → 执行 @tool 函数
       3. 工具结果 → ToolMessage → 返回 LLM
       4. 循环直到生成最终回答
  ↓
同步病例上下文 + 审计日志
  ↓
输出结果
```

---

## 🛠 Tech Stack

| Component | Technology |
|-----------|------------|
| Agent 框架 | LangChain 1.x + LangGraph |
| Web 前端 | Vue 3 + Vite + Pinia + Element Plus |
| Web 后端 | FastAPI + REST + WebSocket |
| 实时通信 | WebSocket（Agent 工具调用过程推送） |
| 对象存储 | MinIO（医学影像文件存储） |
| LLM | DeepSeek API（兼容 OpenAI 协议） |
| RAG 向量库 | ChromaDB（本地持久化） |
| 知识库原文 | `knowledge_base/` 目录（Markdown 格式），`GET /api/knowledge/document/{filename}` |
| Embedding | BGE-Small-ZH-v1.5（本地部署） |
| 视觉模型 | MONAI RetinaNet 3D |
| 深度学习 | PyTorch + CUDA |
| 图像格式 | NIfTI / MetaImage / DICOM |
| 审计日志 | JSONL |

---

## 🚀 Installation

### 环境要求

- Python ≥ 3.10
- PyTorch ≥ 2.0 + CUDA（推荐）
- ≥ 8GB GPU 显存
- Node.js ≥ 18（构建 Web 前端时需要）

### 安装步骤

```bash
# 克隆项目
git clone <repo-url>
cd medical_ai_agent

# 创建虚拟环境（推荐 conda）
conda create -n martin python=3.10
conda activate martin

# 安装 PyTorch（CUDA 版）
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# 安装项目依赖
pip install -r requirements.txt

# 配置环境变量
export DEEPSEEK_API_KEY="your-api-key"
export DEEPSEEK_BASE_URL="https://api.deepseek.com/v1"
```

### 固定测试环境（Windows）

本项目的 Python 测试统一使用本机已有的 `monai_learning` Conda 环境，解释器为 `E:\conda\envs\monai_learning\python.exe`。不要混用系统 Python 或 `.venv`；统一通过测试脚本执行：

```powershell
# 运行全部测试
.\scripts\run_tests.ps1

# 只运行 Web API 测试
.\scripts\run_tests.ps1 tests\test_web_api.py -q
```

如果另一台电脑的环境路径不同，可以临时设置 `MARTIN_TEST_PYTHON` 指向其 `python.exe`。

### 下载模型

1. **MONAI 检测模型**：从 MONAI Model Zoo 下载 `lung_nodule_ct_detection`，放入 `models/vision/`
2. **BGE 嵌入模型**：下载 `bge-small-zh-v1.5`，放入 `models/embedding/`

### 导入知识库

```bash
python scripts/import_knowledge.py
```

---

## ⚡ Quick Start

### 方式 1：Agent 对话模式

```bash
# 推荐：显式启动带会话管理的多轮 Agent
python -m martin agent

# 兼容入口：也会启动同一套交互式 Agent
python main.py
```

启动后可在对话中直接提问，Agent 会自主决定调用工具：

| 用户提问 | Agent 行为 |
|---------|-----------|
| "8mm的结节是怎么样的" | → `retrieve_knowledge(query=...)` 检索知识库 |
| "分析这张CT: data/test.nii.gz" | → `analyze_image` → `retrieve_knowledge` → `generate_report` |
| "患者55岁男性，吸烟10年" | → `update_case_context` 更新病例信息 |

Agent 会模拟医生门诊的沟通方式：先了解就诊原因和患者信息，再结合 CT 检测、医学知识库完成解释与病例报告。它会明确说明自己是 AI 智能体，不代替执业医生诊断。普通中文或英文都直接输入；只有以 `/` 开头的内容才作为系统命令处理。

> 工具调用详情和推理过程写入 `log/agent_thinking/YYYY-MM-DD.log`；模型日志、第三方警告和进度条写入 `log/runtime/YYYY-MM-DD.log`，不会进入问诊界面。

### 方式 2：命令行检测

```bash
# 检测结节
python -m martin detect -i data/ct.nii.gz -o results/detection.json

# 生成报告
python -m martin case -i results/detection.json -o report.md --type detailed
```

### 方式 3：Web Copilot 工作台（推荐）

Martin Web 端已升级为**面向医生的 AI 医学影像辅助分析工作站**。主工作区围绕病例审阅与诊断依据组织，Martin 对话助手按需展开，不再以聊天窗口作为页面中心。

首次运行或前端代码更新后，先构建 Vue 页面：

```bash
cd frontend
npm install
npm run build
cd ..
```

然后使用 `monai_learning` 环境启动 Martin Web 服务：

```powershell
# 已配置 Conda 时
conda activate monai_learning
python -m martin web

# 或直接使用项目固定测试/运行解释器
E:\conda\envs\monai_learning\python.exe -m martin web
```

浏览器访问 `http://127.0.0.1:8000`。

需要使用 CT 文件上传或 OSS 影像分析时，先在独立终端启动本机 MinIO：

```powershell
E:\moani\minio\minio.exe server E:\moani\minio\data --console-address ":9001"
```

MinIO API 地址为 `http://127.0.0.1:9000`，管理控制台地址为 `http://127.0.0.1:9001`。

**开发模式**（前后端分离热重载）：

```bash
# 终端1：后端（monai_learning 环境）
conda activate monai_learning
python -m martin web --reload
# 或：python -m uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload

# 终端2：前端
cd frontend
npm run dev
```

访问 `http://localhost:5173`。

**核心交互流程：**

1. **新建或恢复病例** — 在“病例记录”创建新病例，或点击“继续分析”恢复历史会话、对话记录和 `CaseContext`。
2. **上传 CT 影像** — 在左侧“检查与发现”上传 `.nii` / `.nii.gz` 文件；文件会经 MinIO 与分析接口处理。
3. **审阅 AI 发现** — 分析完成后，左栏列出全部结节；点击某项仅更新前端的当前选中状态，便于逐项复核。
4. **查看诊断信息链** — 中栏展示分析状态与选中结节；右栏串联尺寸、置信度、影像信息、病例风险因素和 RAG 知识引用。
5. **按需使用 Martin Copilot** — 点击右下角 Copilot 展开多轮对话、附件上传和 Agent 工具时间线；WebSocket 与 REST 回退行为保持不变。
6. **生成辅助报告** — 从工作区或“报告工作台”生成 brief / detailed / research 报告。恢复历史病例时，前端会由已持久化的 `CaseContext` 重建检测结果，因此无需重复检测。
7. **查看知识原文** — 点击知识引用的“查看原文”链接，弹出 Drawer 阅读内置指南或上传资料的原文。

### 知识库管理与向量化

左侧导航的“知识库”页面用于维护 RAG 资料：

1. 上传 `.md`、`.txt`、`.pdf`、`.docx` 或 `.csv` 文件；系统会自动切分并写入 Chroma 向量库。
2. 页面会同时列出项目内置指南（只读）和用户上传资料（可删除）。删除上传资料时会同步删除对应向量。
3. 点击“重建全部向量”会重新索引内置指南和全部上传资料，适用于更换 embedding 模型或修复索引时。

上传资料和运行清单保存在 `data/knowledge_uploads/`，不会提交到 Git。向量化依赖本地 BGE embedding 模型，首次加载可能需要一些时间。

### 运行效果

**新版临床影像工作站：恢复已检测病例后，直接审阅 6 个结节、知识依据与报告入口。**

![恢复历史病例后的 Martin 临床影像工作站](docs/images/workstation-restored-case.png)

> 截图使用无患者身份信息的演示病例；当前“影像分析区”展示 AI 的结构化发现，不伪装为真实 CT 切片阅片器。

**基于 CaseContext 生成的辅助分析报告：**

![肺部 CT 智能辅助病例报告](docs/case_report_demo.png)

**知识库文档管理：内置指南、资料来源、向量化状态和上传入口集中管理。截图仅展示项目内置资料。**

![知识库文档管理页面](docs/images/knowledge-document-management.png)

**知识库检索核验：使用 Agent 共用的向量库检索“实性结节 6–8 mm 6–12 个月随访”，展示实际召回来源、相似度与原文片段。**

![知识库检索测试与实际 RAG 召回结果](docs/images/knowledge-retrieval-test.png)

**查看知识库原文（Drawer 展示 Markdown 原文档）：**

![查看知识库原文](docs/knowledge_document_drawer.png)

**CLI 历史会话查看：**

![多轮对话与知识库检索](docs/session_history_demo.svg)

---

## 🗂️ 会话历史与病例恢复

Agent 会将会话保存到 `data/sessions.sqlite`（LangGraph 官方 `SqliteSaver` 管理），应用重启后仍可继续查看历史会话。每个会话以 `thread_id` 隔离；病例上下文与消息历史随同 checkpoint 保存。

| 命令 | 功能 |
|------|------|
| `/list` | 列出所有历史会话 |
| `/open <编号>` | 查看指定会话的完整对话记录 |
| `/switch <编号>` | 切换到指定会话并继续对话 |
| `/new` | 创建并切换到新会话 |
| `/back` | 返回当前会话 |
| `/help` | 查看系统命令帮助 |
| `/exit` | 退出并保存会话 |

例如，输入 `list` 会作为自然语言交给 Agent；输入 `/list` 才会列出历史会话。未知的斜杠命令会显示“不支持的系统命令”。

Web 端的“病例记录”提供同样的会话恢复能力：选择“继续分析”后，前端请求会话详情并恢复消息与 `CaseContext`。其中包含的影像路径、结节列表和检测完成状态会重建为报告输入，因此可从历史病例直接进入“报告工作台”继续生成报告。为兼容早期 SQLite 数据，已有结节列表的旧会话也会被识别为已检测。

## 📚 Documentation

| 文档 | 说明 |
|------|------|
| [🏗 Architecture](docs/ARCHITECTURE.md) | 系统架构设计、模块职责、数据流 |
| [🛠 Development](docs/DEVELOPMENT.md) | 开发过程、技术决策、踩坑记录 |
| [📚 Learning Summary](docs/LEARNING_SUMMARY.md) | 学习笔记与心得体会 |
| [📖 Learning Guide](docs/LEARNING_GUIDE.md) | 当前代码调用链、模块作用与学习顺序 |
| [🧹 Cleanup Audit](docs/CLEANUP_AUDIT.md) | 重复测试、假通过风险和文件清理候选 |
| [🗺 Roadmap](docs/ROADMAP.md) | 未来规划与演进路线 |
| [🌐 Agent Flow](docs/agent_flow.html) | 交互式 Agent 调用流程可视化（浏览器打开） |

---

## 🗺 Future Work

| 状态 | 方向 | 说明 |
|------|------|------|
| ✅ | 单模态肺结节检测 | MONAI RetinaNet 3D |
| ✅ | RAG 知识增强 | ChromaDB + BGE 本地向量库 |
| ✅ | Agent 多轮对话 | LangGraph + SqliteSaver |
| ✅ | 结构化病例记忆 | CaseContext |
| ✅ | Session 持久化 | SqliteSaver + CLI 历史管理 |
| 🔲 | 多模态融合 | 融合 DICOM 元数据、病理报告等 |
| 🔲 | 多 Agent 协作 | 检测 Agent + 诊断 Agent + 报告 Agent |
| 🔲 | 分割能力 | 增加结节分割与体积测量 |
| ✅ | Web UI | Vue 3 + FastAPI 临床影像工作站、可收起 Copilot、病例恢复与报告续写 |
| ✅ | 知识库管理 | Web 上传、自动向量化、删除与全量重建 |
| 🔲 | 批量处理 | 支持队列批量分析 |

---

## 📄 License

MIT License
