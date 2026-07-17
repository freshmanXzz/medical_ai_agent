# Martin 项目调用链与数据流

> 一条完整的“用户提问 → Agent 推理 → 结果返回”链路分析。

---

## 一、整体架构

```
┌─ 浏览器 ──────────────────────────────────────────────────────────────────┐
│  Vue 3 前端 (frontend/src/)                                               │
│  CaseWorkspace.vue → chatStore.ts → api/index.ts (axios)                  │
└──────────────────────────────────┬────────────────────────────────────────┘
                                   │ HTTP POST /api/agent/chat
                                   │ (timeout: 900s)
                                   ▼
┌─ FastAPI 后端 (api/) ─────────────────────────────────────────────────────┐
│  api/main.py           → 路由注册 + 静态前端挂载                           │
│  api/routers/agent.py  → agent_chat() 处理请求                           │
└──────────────────────────────────┬────────────────────────────────────────┘
                                   │ create_agent() → agent.invoke()
                                   ▼
┌─ Agent 核心 (martin/agent/) ──────────────────────────────────────────────┐
│  agent_builder.py  → build_agent() 工厂函数                               │
│  agent.py          → AgentExecutor, create_agent()                        │
│  tools.py          → 4 个 @tool 工具函数                                  │
│  prompt.py         → SYSTEM_PROMPT 系统提示词                             │
│  case_context.py   → CaseContext 结构化病例上下文                          │
│  sessions.py       → SessionManager + SqliteSaver                         │
└──────────────────────────────────┬────────────────────────────────────────┘
                                   │ 工具调用 (Function Calling)
          ┌────────────────────────┼────────────────────────┐
          ▼                        ▼                        ▼
┌─ Vision ───────────┐  ┌─ RAG ─────────────┐  ┌─ LLM ───────────────┐
│ nodule_detector.py │  │ retriever.py      │  │ chat_model.py       │
│ (MONAI RetinaNet)  │  │ vector_store.py   │  │ chain.py (LCEL)     │
│ image_processor.py │  │ embeddings.py     │  │ deepseek_client.py  │
└────────────────────┘  │ text_splitter.py  │  └─────────────────────┘
                        │ document_loader.py│
                        └───────────────────┘
```

---

## 二、一次对话的完整调用链

以用户输入 **"分析 data/ct.nii.gz，生成详细报告"** 为例。

### 第 1 步：前端发起请求

```
CaseWorkspace.vue:234
  chatStore.sendMessage(message, caseContext)
    ↓
chatStore.ts:46
  chatWithAgent(sessionId, userMessage, caseContext)
    ↓
api/index.ts:10
  axios POST /api/agent/chat
  Body: { session_id, user_message, case_context }
```

### 第 2 步：FastAPI 路由接收

```
api/routers/agent.py:24  agent_chat(request)
  │
  ├─ get_default_checkpointer()          → 获取 SqliteSaver 实例
  ├─ create_agent(thread_id, ...)        → 构建 AgentExecutor
  │
  │   调用链:
  │   agent.py:341  create_agent()
  │     → agent.py:182  AgentExecutor.__init__()
  │       ├─ SessionManager.get_case_context()     → 从 DB 恢复 CaseContext
  │       ├─ get_chat_model()                       → ChatOpenAI(DeepSeek)
  │       └─ create_langchain_agent(llm, tools, system_prompt, checkpointer)
  │            → LangGraph 编译后的 StateGraph
  │
  └─ agent.invoke({"input": user_message})
```

### 第 3 步：AgentExecutor.invoke() 内部流程

```
agent.py:221  invoke(inputs)
  │
  ├─ 1. 构造消息: 注入 CaseContext 上下文摘要
  │     context_json + "请基于以上病例信息理解后续问题" + user_input
  │
  ├─ 2. set_case_context(self.case_context)     → ContextVar 隔离
  │
  ├─ 3. self._agent.invoke({"messages": messages}, config)
  │     │
  │     └─ LangGraph 推理循环 (ReAct 模式):
  │         ┌─────────────────────────────────────┐
  │         │  LLM 思考 (DeepSeek)                │
  │         │  ├─ 要求 reasoning 字段 (审计溯源)  │
  │         │  └─ 决定是否调用工具                 │
  │         ├─ [有 tool_calls] → 执行工具函数      │
  │         │    ├─ analyze_image()                │
  │         │    ├─ retrieve_knowledge()           │
  │         │    ├─ update_case_context()          │
  │         │    └─ generate_report()              │
  │         ├─ ToolMessage → 返回 LLM 继续思考     │
  │         └─ [无 tool_calls] → 生成最终回答      │
  │         └─────────────────────────────────────┘
  │
  ├─ 4. _parse_result(messages)     → 提取 output + intermediate_steps
  ├─ 5. _sync_case_context()        → 更新 CaseContext
  └─ 6. reset_case_context(token)   → 恢复上下文
```

### 第 4 步：工具函数内部执行

#### analyze_image → 图像检测

```
tools.py:172  analyze_image(image_path, reasoning)
  │
  ├─ _get_nodule_detector()          → 获取/缓存 NoduleDetector 单例
  ├─ detector.detect(image_path)
  │   │
  │   ├─ _setup_transforms()         → 预处理链:
  │   │   LoadImage → EnsureChannelFirst → Orientation(RAS)
  │   │   → Spacing(1.25mm) → ScaleIntensity(-1024~300) → EnsureType
  │   │
  │   ├─ _prepare_dataloader()       → MONAI Dataset + DataLoader
  │   │
  │   ├─ 滑动窗口推理 (MONAI SlidingWindowInferer):
  │   │   roi_size=[512,512,192], overlap=0.25
  │   │   → RetinaNet 3D 前向传播 → box 回归 + 分类
  │   │
  │   └─ 后处理:
  │       ClipBox → AffineBoxToWorld → ConvertBoxMode(xyzxyz→cccwhd)
  │       → 按 score 排序 → 构建结节列表
  │
  └─ case_context.update_from_detection(result)  → 同步到 CaseContext
```

#### retrieve_knowledge → 知识检索

```
tools.py:234  retrieve_knowledge(detection_context, query, reasoning)
  │
  ├─ get_vector_store()              → ChromaDB 向量库实例
  │
  ├─ 两种模式:
  │   ├─ 查询模式 (query 非空):
  │   │   search_by_query(query, top_k=5, threshold=0.3)
  │   │
  │   └─ 检测模式 (detection_context 非空):
  │       _normalize_detection_result()  → 归一化字段名
  │       search_by_detection(result, top_k=5, threshold=0.7)
  │         → _build_query_from_detection()  → 语义化查询文本
  │         → ChromaDB.similarity_search_with_score()
  │         → 阈值过滤 + 内容去重
  │
  ├─ format_results(results)         → 格式化为 [知识N] + 来源标注
  │
  └─ case_context.set_knowledge_summary()  → 同步知识摘要
```

#### update_case_context → 更新病例信息

```
tools.py:301  update_case_context(user_input, reasoning)
  │
  ├─ CaseContext.extract_patient_info(user_input)
  │   → 从文本提取: 年龄/性别/吸烟史/家族史
  │
  ├─ case_context.update_patient_info(updates)
  └─ case_context.add_clinical_note(user_input)  → 追加临床备注
```

#### generate_report → 生成报告

```
tools.py:339  generate_report(detection_result, report_type, language, case_context, reasoning)
  │
  ├─ json.loads(detection_result)    → 解析检测结果
  ├─ _normalize_detection_result()   → 归一化字段名
  │
  ├─ 第一级: chain_generate_report() (LCEL 链)
  │   链结构:
  │     RAG 检索 (补充知识) → Prompt 模板 → DeepSeek LLM → Markdown 报告
  │   支持 report_type: brief / detailed / research
  │
  ├─ 第二级: _generate_template_report() (模板降级)
  │   基于规则填充报告模板
  │
  └─ 第三级: 错误兜底文本
```

### 第 5 步：结果返回前端

```
agent.py:333  return { "output": "...", "intermediate_steps": [...] }
  ↓
api/routers/agent.py:52  result = agent.invoke(...)
  ↓
解析 intermediate_steps → tool_calls (ToolCallInfo 列表)
获取 case_context.to_dict()
  ↓
返回 ChatResponse { output, session_id, tool_calls, case_context }
  ↓ (JSON)
chatStore.ts:47  messages.push({ role: 'assistant', content: res.data.output })
  ↓
CaseWorkspace.vue  渲染消息列表 + 工具调用状态
```

---

## 三、数据流核心：CaseContext

CaseContext 是整个系统的 **病例记忆中枢**，在请求链路中通过 ContextVar 传递：

```
┌─ API 请求 ────────────────────────────────────────────────────────────────┐
│                                                                            │
│  agent_chat()                                                              │
│    │                                                                       │
│    ├─ create_agent(thread_id)                                              │
│    │   └─ AgentExecutor.__init__()                                         │
│    │       ├─ 从 SqliteSaver 恢复 (跨进程持久化)                           │
│    │       └─ 或从 class 缓存恢复 (同进程内共享)                           │
│    │                                                                       │
│    └─ agent.invoke({...})                                                  │
│        ├─ set_case_context(ctx)  ──────────────────────┐                   │
│        │                                               │ ContextVar        │
│        │  ┌─ LangGraph 推理循环 ──────────────────┐    │ 作用域            │
│        │  │  LLM → tool_calls                      │    │                   │
│        │  │    └─ analyze_image()                  │    │                   │
│        │  │         └─ get_case_context() ←────────┼────┘                   │
│        │  │            .update_from_detection()     │                        │
│        │  │    └─ retrieve_knowledge()              │                        │
│        │  │         └─ get_case_context()           │                        │
│        │  │            .set_knowledge_summary()     │                        │
│        │  └────────────────────────────────────────┘                        │
│        └─ reset_case_context(token)                                         │
│                                                                            │
│  返回 result (含 case_context.to_dict())                                   │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

CaseContext 字段：

| 字段 | 类型 | 写入方 |
|------|------|--------|
| patient_info (age/gender/smoking/family) | dict | update_case_context 工具 |
| image_info | dict | analyze_image 工具 |
| nodules[] | list | analyze_image 工具 |
| knowledge_summary | str | retrieve_knowledge 工具 |
| clinical_notes[] | list | update_case_context, generate_report |

---

## 四、两层记忆架构

| 层级 | 实现 | 存储位置 | 生命周期 |
|------|------|----------|----------|
| 对话记忆 | LangGraph SqliteSaver | `data/sessions.sqlite` | 跨进程持久化 |
| 病例记忆 | CaseContext + ContextVar | 进程内存 | 当前 Python 进程 |

每次 `invoke()`：
1. 从 SqliteSaver 恢复对话历史（LangGraph 自动管理）
2. 从 SqliteSaver 恢复/创建 CaseContext（SessionManager 管理）
3. 注入 CaseContext 摘要到消息开头
4. 工具执行时通过 ContextVar 读取/更新 CaseContext

---

## 五、关键文件速查

| 文件 | 职责 |
|------|------|
| [frontend/src/views/CaseWorkspace.vue](file:///e:/moani/medical_ai_agent/frontend/src/views/CaseWorkspace.vue) | 对话主界面、消息渲染、图像路径输入 |
| [frontend/src/stores/chatStore.ts](file:///e:/moani/medical_ai_agent/frontend/src/stores/chatStore.ts) | Pinia store，管理消息列表、loading 状态 |
| [frontend/src/api/index.ts](file:///e:/moani/medical_ai_agent/frontend/src/api/index.ts) | axios 封装，所有 REST API 调用 |
| [api/main.py](file:///e:/moani/medical_ai_agent/api/main.py) | FastAPI 入口，路由注册，静态文件挂载 |
| [api/routers/agent.py](file:///e:/moani/medical_ai_agent/api/routers/agent.py) | Agent 对话 API (REST + WebSocket) |
| [martin/agent/agent.py](file:///e:/moani/medical_ai_agent/martin/agent/agent.py) | AgentExecutor 核心类，invoke/解析/同步 |
| [martin/agent/agent_builder.py](file:///e:/moani/medical_ai_agent/martin/agent/agent_builder.py) | build_agent() 工厂函数 |
| [martin/agent/tools.py](file:///e:/moani/medical_ai_agent/martin/agent/tools.py) | 4 个 @tool 工具 + CaseContext ContextVar |
| [martin/agent/prompt.py](file:///e:/moani/medical_ai_agent/martin/agent/prompt.py) | SYSTEM_PROMPT 系统提示词 |
| [martin/agent/case_context.py](file:///e:/moani/medical_ai_agent/martin/agent/case_context.py) | CaseContext 结构化病例上下文 |
| [martin/agent/sessions.py](file:///e:/moani/medical_ai_agent/martin/agent/sessions.py) | SessionManager + SqliteSaver 管理 |
| [martin/vision/nodule_detector.py](file:///e:/moani/medical_ai_agent/martin/vision/nodule_detector.py) | MONAI RetinaNet 3D 结节检测器 |
| [martin/rag/retriever.py](file:///e:/moani/medical_ai_agent/martin/rag/retriever.py) | RAG 检索器 (检测模式 + 查询模式) |
| [martin/rag/vector_store.py](file:///e:/moani/medical_ai_agent/martin/rag/vector_store.py) | ChromaDB 向量库封装 |
| [martin/llm/chat_model.py](file:///e:/moani/medical_ai_agent/martin/llm/chat_model.py) | DeepSeek ChatOpenAI 封装 |
| [martin/llm/chain.py](file:///e:/moani/medical_ai_agent/martin/llm/chain.py) | LCEL 声明式报告生成链 |
