# Development — 开发过程与技术总结

---

## 一、项目演进历程

### 第一阶段：单任务模型

最初只是一个肺结节检测脚本：
- 输入：CT 图像路径
- 输出：检测结果 JSON
- 技术：MONAI + PyTorch

### 第二阶段：报告生成器

在检测基础上增加报告生成能力：
- 模板生成（无需 API）
- LLM 智能生成（DeepSeek API）
- 三种报告类型：brief / detailed / research

### 第三阶段：RAG 知识增强

引入知识库检索，解决 LLM 幻觉问题：
- ChromaDB 本地向量库
- BGE 中文嵌入模型
- Lung-RADS 等权威指南导入
- 引用标注机制 [知识N]

### 第四阶段：Agent 化

从流水线模式升级为 Agent 模式：
- LangChain + LangGraph 编排
- 多轮对话能力
- 工具自动调用
- 上下文记忆系统

---

## 二、关键技术决策

### 2.1 为什么选 LangChain 1.x 而非 0.x

**原因：**
- 1.x 是 LangChain 的稳定主线，API 设计更简洁
- `create_agent` 新 API 底层基于 LangGraph，灵活可控
- 与 LangGraph 深度集成，StateGraph 可扩展性强

**迁移代价：**
- 旧版 `initialize_agent` / `AgentExecutor` 全部重写
- 回调系统从旧版 Handler 迁移到新版 Callback
- 记忆系统从 `ConversationBufferMemory` 改为 `MemorySaver`

### 2.2 为什么用两层记忆架构（MemorySaver + CaseContext）

**最初方案：** 只使用 LangGraph 的 MemorySaver，把所有信息塞进 messages。

**问题：**
1. Token 消耗随对话线性增长
2. LLM 需要从对话历史中"提取"信息，不可靠
3. 医学数据需要结构化管理

**最终方案：** 引入 CaseContext 结构化记忆。

**收益：**
- Token 消耗可控（200-500 tokens）
- 上下文注入精准，LLM 理解更可靠
- 结构化数据便于后续处理和持久化
- 业务逻辑与对话历史解耦

**设计思想：**
> 与其让 LLM 在每次对话中"从头阅读历史书"，不如给它一份"结构化摘要报告"。

### 2.3 为什么用 LCEL 而非手动拼装 Prompt

**LCEL（LangChain Expression Language）的优势：**
- 声明式编排，代码清晰
- 自动并行（RunnablePassthrough.assign 中的函数并行执行）
- 流式输出支持
- 类型安全
- 可组合、可测试

### 2.4 为什么选 ChromaDB 而非 FAISS / Milvus

| 方案 | 优势 | 劣势 |
|------|------|------|
| **ChromaDB** | 轻量、本地持久化、LangChain 原生支持 | 大规模性能一般 |
| FAISS | 性能优秀 | 仅内存，需手动持久化 |
| Milvus | 企业级、分布式 | 太重，需要部署服务 |

**选择 ChromaDB 的原因：** 项目规模适中，本地部署即可满足需求，开发效率高。

---

## 三、遇到的问题与解决方案

### 3.1 LangChain 版本兼容问题

**问题：** 项目初期使用 LangChain 0.x 的旧 API，后来升级到 1.x 导致大量导入错误。

**解决：**
- 统一使用 `langchain.agents.create_agent` 新 API
- 记忆系统迁移到 `langgraph.checkpoint.memory.MemorySaver`
- 工具定义统一使用 `@tool` 装饰器

### 3.2 上下文共享问题

**问题：** 工具函数需要访问病例上下文，但工具是被 LangGraph 调用的，无法直接传参。

**解决：** 使用 Python `contextvars` 实现线程级隔离的全局变量。

```python
_case_context_var = contextvars.ContextVar("case_context", default=CaseContext())

# AgentExecutor.invoke() 中设置
token = set_case_context(self.case_context)
try:
    result = self._agent.invoke(...)
finally:
    reset_case_context(token)
```

### 3.3 LLM 生成不稳定

**问题：** LLM 有时生成格式混乱的报告，有时调用失败。

**解决：** 三级降级策略
1. LLM 生成（首选）
2. 模板生成（兜底）
3. 错误信息（完全失败时）

### 3.4 知识库检索相关性不足

**问题：** 直接用检测结果 JSON 作为查询，检索效果差。

**解决：** 构建语义化查询
```python
def _build_query_from_detection(detection_result):
    # 根据结节数量、大小、位置等生成自然语言查询
    # 如："3个肺部结节，最大8.5mm实性结节，Lung-RADS分级"
    ...
```

---

## 四、代码质量保障

### 4.1 测试体系

| 层级 | 测试文件 | 覆盖范围 |
|------|----------|----------|
| 单元测试 | test_agent_tools.py | 工具函数 |
| 单元测试 | test_case_context.py | 病例上下文 |
| 单元测试 | test_logger.py | 日志模块 |
| 集成测试 | test_langchain_pipeline.py | RAG + LLM 全链路 |
| 集成测试 | test_monai.py | MONAI 模型推理 |
| 端到端测试 | test_rag_full_pipeline.py | CT → 检测 → RAG → 报告 |

### 4.2 代码规范

- PEP8 风格
- black 格式化
- isort 导入排序
- 所有公共类/函数带 docstring

---

## 五、可复用的工程模式

### 5.1 @tool + reasoning 参数

所有工具统一增加 `reasoning` 参数，由 LLM 填充调用原因，用于审计溯源。

### 5.2 三级降级策略

LLM 生成 → 模板生成 → 错误信息，保证系统鲁棒性。

### 5.3 结构化上下文注入

CaseContext 模式可以推广到任何领域 Agent：
- 金融 Agent → PortfolioContext
- 法律 Agent → CaseContext（案件上下文）
- 客服 Agent → CustomerContext

### 5.4 contextvars 共享状态

在 Agent 工具间共享状态的标准模式，线程安全，测试友好。
