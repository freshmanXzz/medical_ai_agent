# Martin — Medical AI Agent

> 面向肺部 CT 的智能体：MONAI 影像检测 + RAG 知识增强 + LangChain Agent 编排 + DeepSeek 推理

Martin 是一个开源的医学影像 AI Agent，以肺结节检测为切入点，实现从**影像感知 → 知识检索 → 智能推理 → 报告生成**的完整诊断辅助流程。

---

## ✨ Features

- 👁 **3D 肺结节检测** — 基于 MONAI RetinaNet，支持 NIfTI / MetaImage 格式
- 🔍 **RAG 循证诊断** — ChromaDB + BGE 本地向量库，引用 Lung-RADS 等权威指南
- 🤖 **Agent 智能编排** — LangChain 1.x + LangGraph，多工具自主规划与调用
- 🧠 **结构化病例记忆** — CaseContext 两层记忆架构，Token 高效利用
- 📄 **多类型报告生成** — brief / detailed / research 三档，LCEL 声明式编排
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
| 对话记忆 | LangGraph MemorySaver | 保存完整消息历史 |
| 病例记忆 | CaseContext（结构化） | 患者信息 / 结节数据 / 知识摘要 / 临床备注 |

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
| LLM | DeepSeek API（兼容 OpenAI 协议） |
| RAG 向量库 | ChromaDB（本地持久化） |
| Embedding | BGE-Small-ZH-v1.5（本地部署） |
| 视觉模型 | MONAI RetinaNet 3D |
| 深度学习 | PyTorch + CUDA |
| 图像格式 | NIfTI / MetaImage |
| 审计日志 | JSONL |

---

## 🚀 Installation

### 环境要求

- Python ≥ 3.10
- PyTorch ≥ 2.0 + CUDA（推荐）
- ≥ 8GB GPU 显存

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

**交互示例：**

```
Martin: 您好！我是 Martin 医学智能体，有什么可以帮您？

User: 分析这张CT: data/test.nii.gz

[Agent] 调用工具: analyze_image
[Agent] 调用工具: retrieve_knowledge
[Agent] 调用工具: generate_report

Martin: 已完成分析，检测到 3 个肺结节...
```

### 方式 2：命令行检测

```bash
# 检测结节
python -m martin detect -i data/ct.nii.gz -o results/detection.json

# 生成报告
python -m martin case -i results/detection.json -o report.md --type detailed
```

---

## 📚 Documentation

```
docs/
├── ARCHITECTURE.md         系统架构设计
├── DEVELOPMENT.md          开发过程与技术总结
├── LEARNING_SUMMARY.md     学习笔记与心得体会
└── ROADMAP.md              未来规划
```

---

## 🗺 Future Work

| 状态 | 方向 | 说明 |
|------|------|------|
| ✅ | 单模态肺结节检测 | MONAI RetinaNet 3D |
| ✅ | RAG 知识增强 | ChromaDB + BGE 本地向量库 |
| ✅ | Agent 多轮对话 | LangGraph + MemorySaver |
| ✅ | 结构化病例记忆 | CaseContext |
| 🔲 | 多模态融合 | 融合 DICOM 元数据、病理报告等 |
| 🔲 | 多 Agent 协作 | 检测 Agent + 诊断 Agent + 报告 Agent |
| 🔲 | 分割能力 | 增加结节分割与体积测量 |
| 🔲 | Web UI | 前端可视化交互界面 |
| 🔲 | 批量处理 | 支持队列批量分析 |

---

## 📄 License

MIT License
