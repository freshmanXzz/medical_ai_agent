# Martin — AI Medical Imaging Copilot for Clinicians

> 面向临床医生的 AI 医学影像辅助分析智能体：MONAI 影像检测 + RAG 知识增强 + LangChain Agent 编排 + DeepSeek 推理

Martin 是一个开源的医学影像 AI Copilot，面向**呼吸科 / 胸外科 / 影像科医生**，以肺结节检测为切入点，实现从**影像感知 → 知识检索 → 智能推理 → 报告生成**的完整辅助分析流程。

**核心定位：** 不是面向患者的医疗聊天机器人，而是医生工作流的 AI 影像辅助分析智能体。

---

## ✨ Features

- 👁 **3D 肺结节检测** — 基于 MONAI RetinaNet，支持 NIfTI / MetaImage 格式
- 🔍 **RAG 循证诊断** — ChromaDB + BGE 本地向量库，引用 Lung-RADS 等权威指南
- 🤖 **Agent 智能编排** — LangChain 1.x + LangGraph，多工具自主规划与调用
- 🧠 **结构化病例记忆** — CaseContext 两层记忆架构，Token 高效利用
- 📄 **多类型报告生成** — brief / detailed / research 三档，LCEL 声明式编排
- 💾 **会话持久化** — SqliteSaver + 历史管理，`/list`、`/open`、`/switch`，重启不丢失
- 🌐 **Web Copilot 工作台** — Vue 3 + FastAPI 三栏临床工作区（影像输入 / Agent 对话 / 病例上下文）
- 📎 **ChatGPT 式附件上传** — 聊天栏直接上传 CT，自动识别医学影像并触发分析
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

    subgraph Tools[Tools]
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
| 对话记忆 | LangGraph SqliteSaver | 保存完整消息历史，支持重启恢复 |
| 病例记忆 | CaseContext（结构化） | 患者信息 / 结节数据 / 知识摘要 / 临床备注 |

**右栏面板分离：**

| 面板 | 组件 | 内容 | 定位 |
|------|------|------|------|
| 病例上下文 | PatientContextPanel | 患者信息 / 影像信息 / 检测结果 / 风险因素 | Domain-Specific Context Injection（针对病人） |
| 知识摘要 | KnowledgeSummaryPanel | RAG 检索引用条目（来源 + 摘要 + 查看原文） | 外部参考资料引用（针对知识） |

知识摘要支持"查看原文"：点击引用条目弹出 Drawer 展示知识库 Markdown 原文档（接口：`GET /api/knowledge/document/{filename}`）。

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

Martin Web 端已升级为**面向医生的 AI 医学影像辅助分析工作台**，采用三栏临床布局。

首次运行或前端代码更新后，先构建 Vue 页面：

```bash
cd frontend
npm install
npm run build
cd ..
```

然后使用 `monai_learning` 环境启动 Martin Web 服务：

```bash
conda activate monai_learning
python -m martin web
```

浏览器访问 `http://127.0.0.1:8000`。

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

1. **上传 CT 影像** — 在聊天输入框点击 📎 按钮上传 `.nii` / `.nii.gz` / `.dcm` 文件，系统自动上传到 MinIO 并触发影像分析，无需额外输入文字
2. **Agent 实时过程** — AgentTimeline 组件通过 WebSocket 展示 `analyze_image` → `retrieve_knowledge` → `update_case_context` 等工具调用过程
3. **病例上下文同步** — 右侧 PatientContextPanel 实时展示患者信息、影像结果、结节数据、风险因素（Domain-Specific Context Injection）
4. **知识摘要引用** — Agent 检索知识库后，右栏 KnowledgeSummaryPanel 以引用条目形式展示（来源文件名 + 摘要片段），不再展示大段纯文本
5. **查看原文** — 点击引用条目的"查看原文"链接，弹出 Drawer 展示知识库 Markdown 原文档（如 Lung-RADS 指南、诊疗共识等），支持滚动阅读
6. **多轮追问** — 分析完成后可继续追问"这个结节危险吗？""结合患者年龄重新评估""生成报告"等
7. **报告生成** — 输入"生成报告"，Agent 读取完整 CaseContext 融合影像结果、患者信息、RAG 知识生成辅助报告

### 运行效果

**Web Copilot 首页 Dashboard：**

![Martin Web Copilot Dashboard](docs/web_copilot_dashboard.svg)

**三栏病例工作区（影像输入 / Agent 对话 / 病例上下文）：**

![Martin Web Copilot Workspace](docs/web_copilot_workspace.svg)

**基于 CaseContext 生成的辅助分析报告：**

![肺部 CT 智能辅助病例报告](docs/case_report_demo.png)

**知识摘要引用条目（右栏 KnowledgeSummaryPanel）：**

![知识摘要引用条目](docs/knowledge_summary_panel.png)

**查看知识库原文（Drawer 展示 Markdown 原文档）：**

![查看知识库原文](docs/knowledge_document_drawer.png)

**CLI 历史会话查看：**

![多轮对话与知识库检索](docs/session_history_demo.svg)

---

## 🗂️ 会话历史

Agent 会将会话保存到 `data/sessions.sqlite`（LangGraph 官方 `SqliteSaver` 管理），应用重启后仍可继续查看历史会话。

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
| ✅ | Web UI | Vue 3 + FastAPI 三栏临床工作台 + WebSocket 实时过程 |
| 🔲 | 批量处理 | 支持队列批量分析 |

---

## 📄 License

MIT License
