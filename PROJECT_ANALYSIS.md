# Martin 项目分析文档

> 用于 README 重构前的项目理解与设计思路记录

> **历史文档提示：** 本文保留早期设计背景，部分 MemorySaver、默认模型和入口描述已过期。学习当前实现请以 `docs/LEARNING_GUIDE.md` 和代码为准。

---

## 一、项目整体定位

### 1.1 项目解决什么问题

医学影像诊断中存在两大痛点：

1. **效率问题**：放射科医生每天需要阅读大量 CT 影像，人工标注和诊断耗时耗力
2. **知识偏差**：不同医生对 Lung-RADS 等分级标准的理解和应用存在差异，诊断一致性难以保证

Martin 通过 AI Agent 的方式，将 **深度学习检测 + 知识检索增强 + 大语言模型推理** 结合起来，提供自动化的肺部 CT 结节分析与报告生成能力。

### 1.2 为什么需要这个 Agent

传统的 CAD（计算机辅助检测）系统通常只输出检测结果，不具备：
- 多轮对话交互能力
- 医学知识检索与引用能力
- 自然语言报告生成能力
- 上下文记忆与病例管理能力

Martin 作为一个 Agent，能够自主规划任务、调用工具、引用知识库，最终生成循证的医学报告。

### 1.3 核心用户场景

| 场景 | 用户 | 价值 |
|------|------|------|
| 影像初筛 | 放射科医生 | 快速定位可疑结节，生成初步报告 |
| 教学辅助 | 医学生 / 住院医师 | 对照 AI 分析学习肺结节诊断 |
| 科研工具 | 医学研究者 | 批量分析，生成科研版报告 |
| 知识查询 | 临床医生 | 快速检索 Lung-RADS 等指南 |

---

## 二、Agent 架构分析

### 2.1 Agent 主入口

- **CLI 入口**：`main.py` 和 `martin/__main__.py`
- **Agent 构建工厂**：`martin/agent/agent_builder.py` 的 `build_agent()`
- **执行器**：`martin/agent/agent.py` 的 `AgentExecutor`

### 2.2 Agent Core

```
AgentExecutor
├── _agent: LangChain Agent（由 create_agent 创建，底层为 LangGraph 图）
├── case_context: CaseContext（结构化病例上下文）
├── thread_id: str（会话标识）
└── 日志系统
    ├── 系统日志 → log/YYYY-MM-DD.log
    ├── 思维日志 → log/agent_thinking/YYYY-MM-DD.log
    └── 审计日志 → audit/{session_id}.jsonl
```

### 2.3 LLM 调用方式

- **模型封装**：`martin/llm/chat_model.py` → `get_chat_model()`
- **底层实现**：`langchain_openai.ChatOpenAI`，兼容 OpenAI 协议
- **默认模型**：DeepSeek-chat（也支持阿里云 DashScope 兼容端点）
- **配置来源**：环境变量 `DEEPSEEK_API_KEY` / `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL`

### 2.4 Prompt 设计

- **系统提示词**：`martin/agent/prompt.py` 的 `SYSTEM_PROMPT`
- **报告模板 Prompt**：`martin/llm/chain.py` 中的 `SYS_PROMPT_BRIEF` / `SYS_PROMPT_DETAILED` / `SYS_PROMPT_RESEARCH`
- **核心约束**：诊断结论必须基于知识库，引用标注来源

### 2.5 Tools / Skills

| 工具 | 功能 | 参数 |
|------|------|------|
| `analyze_image` | 肺部 CT 结节检测 | `image_path`, `reasoning` |
| `retrieve_knowledge` | 检索医学知识库 | `detection_context`, `reasoning` |
| `generate_report` | 生成病例报告 | `detection_result`, `report_type`, `language`, `case_context`, `reasoning` |
| `update_case_context` | 更新病例上下文 | `user_input`, `reasoning` |

所有工具都包含 `reasoning` 参数，用于医疗审计溯源。

### 2.6 Workflow

```
用户输入
  ↓
AgentExecutor.invoke()
  ├─ 构建 messages（注入 CaseContext）
  ├─ 设置 contextvars（共享病例上下文）
  └─ LangGraph StateGraph 循环：
       1. LLM 推理 → 判断是否调用工具
       2. 有 tool_calls → 执行对应 @tool 函数
       3. 工具结果作为 ToolMessage 返回给 LLM
       4. 循环直到 LLM 输出最终回答
  ↓
解析结果 + 同步病例上下文
  ↓
返回 {"output": str, "intermediate_steps": [...]}
```

### 2.7 Memory

**两层记忆架构：**

1. **对话历史记忆**：LangGraph `MemorySaver`（基于 `thread_id`）
   - 保存完整的 messages 列表
   - 支持多轮对话恢复

2. **结构化病例记忆**：`CaseContext`（自定义）
   - `patient_info`：患者信息（年龄/性别/吸烟史/家族史）
   - `image_info`：影像信息
   - `nodules`：结节列表
   - `knowledge_summary`：知识摘要
   - `clinical_notes`：临床备注

两者通过 `thread_id` 关联，在每次 invoke 时合并注入。

### 2.8 RAG 知识增强流程

```
检测结果字典
  ↓
_build_query_from_detection() → 语义化查询
  ↓
ChromaDB 相似度检索（BGE 嵌入）
  ↓
阈值过滤 + 去重
  ↓
format_results() → 带 [知识N] 标注的文本
  ↓
注入 LLM Prompt
```

知识库来源：Lung-RADS、CT 肺结节诊断专家共识、肺结节诊疗指南等。

### 2.9 多模态能力

- **视觉模态**：MONAI RetinaNet 3D 检测肺部 CT 结节
- **文本模态**：DeepSeek LLM 进行推理和报告生成
- **模态桥接**：检测结果 → 结构化 JSON → 自然语言描述 → LLM

---

## 三、技术实现分析

### 3.1 框架选型

| 层级 | 框架 | 职责 / 版本 |
|------|------|-------------|
| Agent 编排 | LangChain create_agent + LangGraph 运行时 | LangChain 构建 Agent、模型、工具与 middleware；LangGraph 管理图、状态与 checkpoint |
| 深度学习 | PyTorch + MONAI | torch 2.7.1+cu118 |
| 向量数据库 | ChromaDB | langchain_chroma |
| 嵌入模型 | BGE-Small-ZH-v1.5 | 本地部署 |
| LLM | DeepSeek API | 兼容 OpenAI 协议 |

### 3.2 模型

| 模型 | 用途 | 部署方式 |
|------|------|----------|
| RetinaNet 3D (MONAI Model Zoo) | 肺结节检测 | 本地加载 .pt 权重 |
| BGE-Small-ZH-v1.5 | 文本嵌入 | 本地加载 |
| DeepSeek-chat | 推理与报告生成 | API 调用 |

### 3.3 数据处理流程

```
NIfTI / MHD 图像
  ↓
ImageProcessor（格式转换、信息提取）
  ↓
NoduleDetector（MONAI 推理 + NMS）
  ↓
结构化 JSON（{image, total_nodules, nodules: [...]}）
```

### 3.4 检索流程

```
检测结果 → 查询构建 → 向量检索 → 过滤去重 → 格式化输出
```

### 3.5 推理流程

```
LCEL 链 (chain.py):
RunnablePassthrough.assign(
    knowledge_context = _build_knowledge_context,
    nodules_detail = _build_nodules_detail,
    patient_info = _build_patient_info,
)
  |
  ↓
diagnosis_prompt (ChatPromptTemplate)
  |
  ↓
ChatOpenAI (DeepSeek)
  |
  ↓
StrOutputParser
  |
  ↓
报告 Markdown
```

三级降级策略：LLM 生成 → 模板生成 → 错误信息。

### 3.6 输出流程

- **检测结果**：JSON 文件，按日期目录分类
- **报告**：Markdown 格式，支持 brief / detailed / research 三种类型
- **审计日志**：JSONL 格式，记录每次工具调用和推理过程

---

## 四、README 设计思路

### 4.1 核心信息保留

README 只保留：
1. 项目一句话介绍
2. 核心特性（Features）
3. 架构图（Mermaid）
4. 工作流
5. 技术栈表格
6. 安装与快速开始
7. Quick Demo
8. 文档链接
9. Future Work（区分已实现/计划）
10. License

### 4.2 拆分到 docs/ 的内容

| 文件 | 内容来源 |
|------|----------|
| `docs/ARCHITECTURE.md` | Agent 架构详解、模块职责、数据流 |
| `docs/DEVELOPMENT.md` | 开发过程、技术选型决策、遇到的问题 |
| `docs/LEARNING_SUMMARY.md` | 学习总结、AI Vibe Coding 经验 |
| `docs/ROADMAP.md` | 未来规划 |

### 4.3 风格定位

参考优秀 AI Agent 开源项目（如 LangChain、AutoGPT 等）：
- 简洁专业
- 架构清晰
- 易于二次开发
- Emoji 适量点缀
- Mermaid 图可视化
