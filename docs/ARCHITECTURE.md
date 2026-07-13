# Architecture — 系统架构设计

---

## 一、整体架构

Martin 采用**分层架构**，从上到下依次为：

```
┌─────────────────────────────────────────────────┐
│              API / CLI 入口层                     │
│  main.py / martin/__main__.py                   │
├─────────────────────────────────────────────────┤
│              Agent 编排层                         │
│  martin/agent/                                  │
│  ├─ agent.py        (AgentExecutor)             │
│  ├─ agent_builder.py (build_agent)              │
│  ├─ tools.py        (@tool 工具集)               │
│  ├─ case_context.py (结构化病例上下文)           │
│  ├─ prompt.py       (系统提示词)                 │
│  └─ audit.py        (审计日志)                   │
├─────────────────────────────────────────────────┤
│              业务逻辑层                           │
│  LLM 模块          RAG 模块         Vision 模块  │
│  martin/llm/       martin/rag/      martin/vision/│
│  ├─ chat_model.py   ├─ retriever.py  ├─ nodule_detector.py│
│  ├─ chain.py        ├─ vector_store.py└─ image_processor.py│
│  └─ deepseek_client.py├─ embeddings.py           │
│                     ├─ text_splitter.py           │
│                     └─ document_loader.py         │
├─────────────────────────────────────────────────┤
│              基础设施层                           │
│  config.py / utils/logger.py / result_manager.py │
└─────────────────────────────────────────────────┘
```

---

## 二、Agent 核心架构

### 2.1 AgentExecutor

`AgentExecutor` 是对 LangGraph Agent 的封装，提供统一的调用接口：

```python
class AgentExecutor:
    def __init__(self, llm, tools, verbose=False, thread_id="default"):
        self._agent = create_langchain_agent(...)  # LangGraph StateGraph
        self.case_context = CaseContext()
        self.thread_id = thread_id
        ...

    def invoke(self, inputs):
        # 1. 构建 messages（注入 CaseContext）
        # 2. 设置 contextvars（共享病例上下文）
        # 3. 调用 LangGraph
        # 4. 解析结果 + 同步病例上下文
        return {"output": ..., "intermediate_steps": [...]}
```

### 2.2 两层记忆架构

| 层级 | 实现 | 存储内容 | 生命周期 |
|------|------|----------|----------|
| **对话记忆** | LangGraph MemorySaver | 完整 messages 列表 | 同一会话内持久化 |
| **病例记忆** | CaseContext（结构化数据类） | 患者信息/结节/知识摘要/临床备注 | 同一会话内持久化 |

**设计考量**：

- 对话记忆交给 LangGraph 原生管理，保证多轮对话的完整性
- 病例记忆独立管理，实现结构化、可控的 Token 利用
- 两者通过 `thread_id` 关联，在每次 invoke 时合并注入

### 2.3 工具系统

4 个 `@tool` 装饰的工具函数：

| 工具 | 输入 | 输出 | 副作用 |
|------|------|------|--------|
| `analyze_image` | image_path, reasoning | 检测结果文本 | 更新 CaseContext.nodules / image_info |
| `retrieve_knowledge` | detection_context, reasoning | 知识库文本 | 更新 CaseContext.knowledge_summary |
| `generate_report` | detection_result, report_type, ... | Markdown 报告 | 无（纯生成） |
| `update_case_context` | user_input, reasoning | 确认文本 | 更新 CaseContext.patient_info / clinical_notes |

所有工具包含 `reasoning` 参数（LLM 填充），用于审计溯源。

---

## 三、RAG 知识增强架构

### 3.1 检索流程

```
检测结果字典
  ↓
_build_query_from_detection()
  ↓ 生成语义化查询（如"3个肺部结节，最大8.5mm实性结节"）
ChromaDB 相似度检索
  ↓
阈值过滤 + 去重
  ↓
format_results()
  ↓ 带 [知识N] 标注
注入 LLM Prompt
```

### 3.2 查询构建策略

根据检测结果动态构建查询：
- 结节数量：单个 / 少量 / 多发
- 结节大小：微小结节 / 小结节 / 大结节
- 密度类型（预留）：实性 / 部分实性 / 磨玻璃

### 3.3 知识库来源

- Lung-RADS v2022 分级标准
- CT 肺结节诊断专家共识（2023）
- 肺结节诊疗指南（2024）
- 肺部影像报告和数据系统

---

## 四、LLM 推理链架构

### 4.1 LCEL 声明式编排

```python
chain = (
    RunnablePassthrough.assign(
        knowledge_context = _build_knowledge_context,   # 并行：RAG 检索
        nodules_detail = _build_nodules_detail,         # 并行：格式化结节
        patient_info = _build_patient_info,             # 并行：提取患者信息
    )
    | diagnosis_prompt       # ChatPromptTemplate
    | model                  # ChatOpenAI(DeepSeek)
    | StrOutputParser()      # 字符串解析
)
```

### 4.2 三级降级策略

1. **LLM 生成**：首选，智能且高质量
2. **模板生成**：LLM 失败时降级，保证输出
3. **错误信息**：完全失败时返回错误提示

---

## 五、数据流

### 5.1 端到端数据流

```
用户输入（自然语言）
  ↓
AgentExecutor.invoke()
  ├─ CaseContext.to_context_string() → 上下文字符串
  ├─ messages = [上下文, 用户输入]
  └─ LangGraph 循环：
       LLM → tool_calls?
         ├─ Yes → 执行工具 → 更新 CaseContext → ToolMessage → 回到 LLM
         └─ No  → 最终回答
  ↓
输出结果 + 审计日志
```

### 5.2 跨工具上下文共享

使用 Python `contextvars` 实现线程隔离的全局上下文：

```python
# tools.py
_case_context_var = contextvars.ContextVar("case_context", default=CaseContext())

def get_case_context() -> CaseContext:
    return _case_context_var.get()
```

在 `AgentExecutor.invoke()` 中设置，工具函数内部通过 `get_case_context()` 获取。

---

## 六、日志与审计

### 6.1 三类日志

| 日志类型 | 路径 | 内容 |
|----------|------|------|
| 系统日志 | `log/YYYY-MM-DD.log` | 模块运行信息、错误 |
| 思维日志 | `log/agent_thinking/YYYY-MM-DD.log` | LLM 调用、工具调用参数、完整 reasoning |
| 审计日志 | `audit/{session_id}.jsonl` | 结构化工具调用记录，可用于医疗审计 |

### 6.2 审计日志格式

```json
{
  "timestamp": "2024-07-13T10:00:00",
  "tool_name": "analyze_image",
  "args": {"image_path": "/path/ct.nii.gz"},
  "output_summary": "检测到3个结节...",
  "reasoning": "用户请求分析CT图像..."
}
```

---

## 七、关键设计决策

| 决策 | 选择 | 原因 |
|------|------|------|
| Agent 框架 | LangChain 1.x + LangGraph | 生态成熟，StateGraph 灵活可控 |
| LLM 接入 | ChatOpenAI 兼容层 | 可切换不同 OpenAI 兼容模型 |
| 向量库 | ChromaDB 本地 | 轻量、无需服务、本地持久化 |
| 记忆方案 | 双层（MemorySaver + CaseContext） | 对话历史 + 结构化数据各司其职 |
| 报告生成 | LCEL 链 + 三级降级 | 声明式编排 + 鲁棒性保证 |
| 上下文注入 | 结构化字符串注入 | Token 高效、上下文精准 |
