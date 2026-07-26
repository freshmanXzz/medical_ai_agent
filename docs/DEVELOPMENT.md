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
- LangChain `create_agent` 编排；LangGraph 作为状态、路由与 checkpoint 运行时
- 多轮对话能力
- 工具自动调用
- 上下文记忆系统

---

## 二、关键技术决策

### 2.1 为什么采用 LangChain create_agent 与 LangGraph 运行时

**当前选择：**
- `langchain.agents.create_agent` 是官方 Agent 构图入口，底层使用 LangGraph 运行时
- `MartinState` 与 LangGraph Checkpointer 管理结构化病例状态和持久化
- LangChain `@dynamic_prompt` middleware 在每轮模型调用前注入 `CaseContext`
- LangChain 1.x 同时提供 `ChatOpenAI`、`@tool`、LCEL 和 RAG 生态组件

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

### 3.1 LangGraph 预制 Agent API 迁移

**问题：** `langgraph.prebuilt.create_react_agent` 面临弃用，需要迁移到 LangChain 1.x 推荐的高层 Agent API。

**当前实现：**
- Agent 使用 `langchain.agents.create_agent`，动态 Prompt 由 `@dynamic_prompt` middleware 提供
- 记忆系统使用 LangGraph Checkpointer（生产环境为 `SqliteSaver`）
- 工具定义使用 LangChain `@tool` 装饰器

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

### 3.5 Agent 翻译工具 JSON 字段导致检索结果为空

**现象：** Agent 完成 CT 检测后提示“未检索到相关医学知识”，随后生成的报告也错误地写成“未发现结节”。这很容易被误认为 ChromaDB 没有初始化。

**排查证据：**

- `ChromaDB/medical_knowledge` 集合实际包含 63 条数据，直接查询可以命中 `Lung-RADS_v2022.md`。
- 审计日志中的 `analyze_image` 结果包含 6 个结节。
- Agent 调用下游工具时把标准字段翻译成了 `结节总数`、`结节列表`、`最大直径_mm`、`置信度`。
- `_normalize_detection_result()` 原先只识别英文别名，因此归一化后得到 `total_nodules=0`、`nodules=[]`；检索器在空列表检查处提前返回，报告生成也沿用了错误的空结果。

**根因：** LLM 生成的工具参数并不保证字段名与上一个工具的输出完全一致。自然语言提示可以降低字段漂移概率，但不能代替代码层的输入兼容和校验。

**解决：**

1. 在 `_normalize_detection_result()` 中同时兼容标准英文键和已观察到的中文别名。
2. 在 Agent 系统提示词中要求工具调用 JSON 保持标准英文字段名。
3. 用审计日志中真实出现的中文 JSON 增加回归测试，分别覆盖知识检索和报告生成。

**经验：** 遇到“知识库为空”类问题，应分层验证“数据库是否有数据、检索函数是否收到有效查询、Agent 是否正确传递工具参数”，不能只根据最终回复判断初始化状态。

### 3.6 向量已入库，但 Agent 未引用对应指南（2026-07-24）

**现象：** `05_肺结节诊疗指南2024.md` 已存在于内置资料配置中，但 Agent 在回答“肺癌筛查高危人群标准的依据/来源”时声称本次检索只有 `Lung-RADS_v2022.md`，并把筛查阈值描述为通用知识。这会让使用者误以为 2024 指南没有导入。

**分层排查证据：**

1. 源文件、`configs/knowledge_base.yaml` 和严格加载器均包含该指南。
2. 排查时已有 Chroma 集合虽有 86 条向量，但该指南的向量块数为 0；这是旧集合在文件名与 CSV 加载问题修复前构建遗留的状态。
3. 通过 `POST /api/knowledge/rebuild` 重建后，集合包含 112 个文本块；其中该指南有 7 个文本块，每个嵌入维度为 512。
4. 使用“肺癌筛查高危人群、50 岁、20 包年”检索时，指南的“筛查与早期发现”章节被实际召回，包含年龄 50–80 岁和吸烟史 ≥20 包年的原文。
5. 根因不再是向量缺失，而是 Agent 在已有 CT 检测上下文时倾向仅传 `detection_context`。该路径生成的是“结节分级与随访”查询，容易只召回 Lung-RADS，丢失用户对“筛查标准来源”的主题。

**解决：**

1. 在系统提示词中将“来源、证据、依据、适用指南”列为 `retrieve_knowledge` 的明确触发条件。
2. 要求此类追问必须把当前问题及关键条件填入 `retrieve_knowledge.query`，不能只传检测结果。
3. 规定来源型回答只能引用本次工具返回的资料；未召回的指南、研究、机构、阈值或统计数据不能以“补充说明”形式混入。
4. 更新提示词回归测试，并重启 Web 后端加载规则。

**验证：**

- 单元测试验证提示词包含来源可追溯与 `query` 调用约束。
- 隔离 Agent 和实际 `/api/agent/chat` 调用均触发 `retrieve_knowledge`，并返回《肺结节诊疗指南（2024）》的高危筛查标准。

**经验：** “资料可加载”“存在向量”“能被正确检索”“最终回答准确引用”是四个独立的验收层。医疗 RAG 不能只验证向量库条数或最终文本，必须同时验证来源元数据、主题检索和 Agent 的工具参数。

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
