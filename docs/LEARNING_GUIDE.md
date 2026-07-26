# Martin 医学AI智能体项目学习指南

> **项目定位**：基于 MONAI、LangChain Agent 编排与 LangGraph 运行时的肺部CT结节检测智能体，实现"感知—知识—决策"三层架构的端到端医学AI系统

---

## 一、项目整体架构

### 1.1 三层架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                        用户输入                              │
│              (CT图像路径 / 自然语言问题)                      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Agent Core (决策层)                      │
│       LangChain create_agent + LangGraph + DeepSeek         │
│            ┌─────────────────────────────────────────┐      │
│            │  推理循环: 思考 → 工具调用 → 观察 → 决策  │      │
│            └─────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────┘
                              │
            ┌─────────────────┼─────────────────┐
            ▼                 ▼                 ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│  Vision Module  │ │   RAG Module    │ │   LLM Module    │
│   (感知层)      │ │   (知识层)      │ │   (决策层)      │
│                 │ │                 │ │                 │
│  MONAI          │ │  ChromaDB       │ │  DeepSeek       │
│  RetinaNet3D    │ │  bge-small-zh   │ │  LCEL Chain     │
│  NIfTI/MHD      │ │  肺结节指南      │ │  报告生成       │
└─────────────────┘ └─────────────────┘ └─────────────────┘
```

### 1.2 模块职责划分

| 模块 | 职责 | 核心文件 |
|------|------|----------|
| `martin/agent/` | Agent编排、工具调用、会话管理 | agent.py, tools.py, sessions.py, case_context.py |
| `martin/llm/` | 大模型调用、报告生成链 | chain.py, chat_model.py, deepseek_client.py |
| `martin/rag/` | 知识库检索、向量存储 | retriever.py, vector_store.py, embeddings.py |
| `martin/vision/` | 医学影像处理、结节检测 | nodule_detector.py, image_processor.py |
| `martin/utils/` | 日志、结果管理、运行时工具 | logger.py, result_manager.py |
| `martin/config.py` | 全局配置管理 | config.py |

---

## 二、核心模块详解

### 2.1 Agent Core（智能体核心）

#### 2.1.1 Agent执行器 (`martin/agent/agent.py`)

**核心概念**：
- `AgentExecutor`：基于 LangChain `create_agent`、`MartinState`、动态 Prompt middleware 与 Checkpointer 构建
- `thread_id`：会话标识，同一 thread_id 的多次调用共享对话历史
- `CaseContext`：病例上下文，跨工具共享的结构化医学数据

**执行流程**：
```python
# 1. 构造消息（注入病例上下文）
context_str = self.case_context.to_context_string(max_nodules=5)
if context_str:
    messages = [
        ("human", f"【当前病例上下文】\n{context_str}\n\n请基于以上病例信息理解后续问题。"),
        ("human", user_input),
    ]

# 2. 配置 thread_id 和回调
config = {"configurable": {"thread_id": self.thread_id}}
if self.verbose:
    config["callbacks"] = [AgentLoggingHandler()]

# 3. 设置上下文（contextvars）
token = set_case_context(self.case_context)

# 4. 执行推理
result = self._agent.invoke({"messages": messages}, config=config)

# 5. 同步结果到上下文
self._sync_case_context_from_steps(parsed_result.get("intermediate_steps", []))
```

**关键设计**：
- **上下文注入**：每次推理前自动注入病例上下文，确保 Agent 了解当前病例状态
- **contextvars 机制**：实现工具间的线程安全上下文共享
- **结果同步**：根据工具执行结果自动更新病例上下文（如知识检索后更新知识摘要）

#### 2.1.2 工具定义 (`martin/agent/tools.py`)

**四个核心工具**：

| 工具 | 功能 | 输入 | 输出 |
|------|------|------|------|
| `analyze_image` | CT影像结节检测 | `image_path` | 可读检测文本；结构化结果同步到 CaseContext |
| `retrieve_knowledge` | 医学知识库检索 | `detection_context` / `query` | 知识片段（带来源标注） |
| `update_case_context` | 更新病例上下文 | `user_input` | 更新摘要 |
| `generate_report` | 生成病例报告 | `detection_result`, `report_type` | Markdown报告 |

**工具实现要点**：
- 使用 `@tool` 装饰器（`langchain_core.tools.tool`）
- 每个工具自动同步结果到 `CaseContext`
- `retrieve_knowledge` 支持两种模式：
  - **检测模式**：基于检测结果构建查询（结节数量、直径）
  - **查询模式**：自由文本直接检索

#### 2.1.3 病例上下文 (`martin/agent/case_context.py`)

**CaseContext 数据结构**：
```python
self.patient_info = {
    "age": None,           # 年龄
    "gender": None,        # 性别
    "smoking_history": None,   # 吸烟史
    "family_history": None     # 家族史
}
self.image_info = {
    "modality": "胸部CT",   # 影像类型
    "image_path": None,     # 图像路径
    "image_name": None      # 图像名称
}
self.nodules = []          # 结节列表
self.knowledge_summary = ""  # 知识摘要
self.clinical_notes = []    # 临床备注
```

**核心方法**：
- `update_from_detection(result)`：从检测结果更新影像信息和结节列表
- `extract_patient_info(text)`：从自然语言文本抽取患者信息（正则匹配）
- `to_context_string()`：生成适合注入 LLM 的格式化上下文字符串
- `to_dict()` / `from_dict()`：序列化/反序列化

#### 2.1.4 会话管理 (`martin/agent/sessions.py`)

**核心组件**：
- `SessionManager`：管理多个会话，支持列表、加载、切换
- `SqliteSaver`：LangGraph 官方 SQLite Checkpointer，持久化对话历史
- 展示信息：thread_id、首条用户消息标题、最新 checkpoint 时间
- SQLite 保存 LangGraph 消息；CaseContext 对象本身仍是进程内缓存

**CLI命令**：
```
/list          列出历史会话
/open <编号>   查看历史会话
/switch <编号> 切换并继续历史会话
/new           创建新会话
/back          返回当前会话
/help          查看命令帮助
/exit          退出程序
```

---

### 2.2 LLM Module（大模型模块）

#### 2.2.1 LCEL链 (`martin/llm/chain.py`)

**LCEL (LangChain Expression Language)** 声明式编排：

```python
chain = (
    RunnablePassthrough.assign(
        knowledge_context=lambda x: _build_knowledge_context(
            x.get("detection_result"), config.top_k
        ),
        nodules_detail=lambda x: _build_nodules_detail(
            x.get("detection_result"), x.get("report_type", "detailed")
        ),
        patient_info=lambda x: _build_patient_info(x.get("case_context")),
    )
    | diagnosis_prompt
    | model
    | StrOutputParser()
)
```

**执行流程**：
1. **并行处理**：同时构建知识库上下文、结节详情、患者信息
2. **Prompt构建**：使用 `ChatPromptTemplate` 组装系统提示词和用户提示词
3. **LLM调用**：调用 DeepSeek 大模型
4. **输出解析**：使用 `StrOutputParser` 转换为字符串

**三种报告类型**：

| 类型 | 特点 | 应用场景 |
|------|------|----------|
| `brief` | 简洁摘要 | 快速浏览 |
| `detailed` | 完整报告（患者资料、检查信息、影像所见、风险评估、建议） | 常规诊断 |
| `research` | 科研级报告（表格、统计分析、JSON数据） | 研究用途 |

**降级策略**：
1. **第一级**：LCEL链（LLM生成）
2. **第二级**：模板生成（LLM失败时）
3. **第三级**：基本错误信息（模板也失败时）

#### 2.2.2 提示词设计 (`martin/agent/prompt.py`)

**核心原则**：
- 强制基于知识库资料，不得凭空编造
- 引用知识库时标注来源（[知识1]、[知识2]）
- 未提供的信息必须标注为"未提供"，不得推断
- 资料不足时不得强行给出 Lung-RADS 类别

---

### 2.3 RAG Module（知识检索模块）

#### 2.3.1 检索器 (`martin/rag/retriever.py`)

**检索流程**：
```python
def search_by_detection(detection_result, top_k=5, threshold=0.7):
    # 1. 构建语义化查询
    query = _build_query_from_detection(detection_result)
    #    例如："3个肺部结节 小结节 最大直径7.2mm Lung-RADS分级 诊断标准"
    
    # 2. 执行向量检索
    results = retriever.invoke(query)
    
    # 3. 多结节时额外检索最大结节
    if len(nodules) > 1:
        size_query = f"肺部结节直径{max_diameter}mm 大小分级"
        size_results = retriever.invoke(size_query)
    
    # 4. 去重、过滤、截断
    results = _deduplicate_results(results)
    filtered = [doc for doc in results if doc.metadata.get("score") >= threshold]
    return filtered[:top_k]
```

**两种检索模式**：
- `search_by_detection()`：基于检测结果的上下文感知检索
- `search_by_query()`：自由文本查询，用于用户直接提问

#### 2.3.2 向量存储 (`martin/rag/vector_store.py`)

**技术栈**：
- 向量数据库：ChromaDB（轻量级，无需额外服务）
- 嵌入模型：bge-small-zh（中文语义理解）
- 知识库来源：肺结节诊疗指南、Lung-RADS分级标准、ICD-11编码等

**初始化流程**：
```python
# 首次使用前必须显式导入知识库
python scripts/import_knowledge.py

# 运行时只打开已有 ChromaDB；不存在时返回“知识库未初始化”
vector_store = get_vector_store()
```

---

### 2.4 Vision Module（视觉模块）

#### 2.4.1 结节检测器 (`martin/vision/nodule_detector.py`)

**技术栈**：
- 框架：MONAI（NVIDIA Medical Open Network for AI）
- 模型：RetinaNet3D（3D目标检测）
- 骨干网络：ResNet50（3D版本）
- 输入格式：NIfTI（`.nii`, `.nii.gz`）或 MHD

**检测流程**：
```python
def detect(image_path):
    # 1. 预处理变换
    preprocessing = Compose([
        LoadImaged(keys="image"),           # 加载图像
        EnsureChannelFirstd(keys="image"),   # 添加通道维度
        Orientationd(keys="image", axcodes="RAS"),  # 标准化方向
        Spacingd(keys="image", pixdim=[0.703125, 0.703125, 1.25]),  # 重采样
        ScaleIntensityRanged(keys="image", a_min=-1024.0, a_max=300.0),  # HU值归一化
        EnsureTyped(keys="image")
    ])
    
    # 2. 滑动窗口推理（处理大尺寸CT）
    self.detector.set_sliding_window_inferer(
        roi_size=[512, 512, 192],
        overlap=0.25
    )
    
    # 3. 后处理变换（坐标转换）
    postprocessing = Compose([
        ClipBoxToImaged(...),
        AffineBoxToWorldCoordinated(...),   # 图像坐标 → 世界坐标
        ConvertBoxModed(src_mode="xyzxyz", dst_mode="cccwhd")  # 格式转换
    ])
    
    # 4. 解析结果
    nodules = []
    for box, score in zip(boxes, scores):
        nodules.append({
            "index": j + 1,
            "score": float(score),
            "center": {"x": box[0], "y": box[1], "z": box[2]},
            "dimensions": {"width": box[3], "height": box[4], "depth": box[5]},
            "diameter": float(max(box[3], box[4], box[5]))
        })
```

**关键医学影像概念**：
- **HU值**：CT值单位，-1024为空气，300为软组织，预处理时归一化到[0, 1]
- **RAS坐标**：医学影像标准坐标系（Right-Anterior-Superior）
- **滑动窗口**：处理大尺寸CT时，分块推理后合并结果
- **NMS（非极大值抑制）**：去除重叠检测框

---

## 三、数据流向

### 3.1 完整推理流程

```
用户输入: "分析这张CT图像"
         │
         ▼
┌──────────────────────────────────────┐
│  Agent 推理循环 (LangGraph)          │
│  ┌────────────────────────────────┐  │
│  │ 1. LLM思考: 需要分析图像        │  │
│  │ 2. 调用 analyze_image 工具     │  │
│  │ 3. 观察结果: 检测到3个结节      │  │
│  │ 4. 更新 CaseContext            │  │
│  │ 5. LLM思考: 需要检索知识        │  │
│  │ 6. 调用 retrieve_knowledge     │  │
│  │ 7. 观察结果: 获取指南知识       │  │
│  │ 8. 更新 CaseContext            │  │
│  │ 9. LLM思考: 需要生成报告        │  │
│  │ 10. 调用 generate_report       │  │
│  │ 11. 返回最终报告               │  │
│  └────────────────────────────────┘  │
└──────────────────────────────────────┘
```

### 3.2 模块间数据传递

```
用户输入
    │
    ▼
martin/agent/agent.py (AgentExecutor)
    │
    ├──► analyze_image ──► martin/vision/nodule_detector.py
    │                          │
    │                          ▼
    │                   NIfTI/MHD图像
    │                          │
    │                          ▼
    │                   RetinaNet3D检测
    │                          │
    │                          ▼
    │                   结节列表 (dict)
    │                          │
    │                          ▼
    │                   CaseContext.update_from_detection()
    │
    ├──► retrieve_knowledge ──► martin/rag/retriever.py
    │                                │
    │                                ▼
    │                         ChromaDB向量检索
    │                                │
    │                                ▼
    │                         知识片段 (Document列表)
    │                                │
    │                                ▼
    │                         CaseContext.set_knowledge_summary()
    │
    └──► generate_report ──► martin/llm/chain.py
                               │
                               ▼
                        LCEL链 (RAG检索 + Prompt + LLM)
                               │
                               ▼
                        Markdown报告
```

---

## 四、关键技术点总结

### 4.1 LangChain / LangGraph 核心概念

| 概念 | 作用 | 项目应用 |
|------|------|----------|
| `create_agent` | 创建 Agent，并编译到底层 LangGraph 图 | LangChain，`martin/agent/agent.py` |
| `@dynamic_prompt` | 每轮模型调用前动态注入病例上下文 | LangChain middleware |
| `MartinState` / `Checkpointer` | 管理状态与会话持久化 | LangGraph / SqliteSaver |
| `@tool` | 将业务函数定义为模型可调用工具 | LangChain，六个核心工具 |
| `LCEL` | 声明式报告生成链 | LangChain，`martin/llm/chain.py` |
| `ChatOpenAI` / RAG 组件 | 模型适配、文档/切分/嵌入/向量库集成 | LangChain 生态 |
| `thread_id` | 会话唯一标识 | LangGraph checkpoint 跨调用恢复 |

### 4.2 医学影像处理要点

| 概念 | 说明 |
|------|------|
| NIfTI格式 | 医学影像标准格式，`.nii` 或 `.nii.gz` |
| MHD格式 | MetaImage格式，由 `.mhd` 和 `.raw` 文件组成 |
| HU值 | CT值，-1024~300范围归一化 |
| RAS坐标 | 右-前-上坐标系，医学影像标准 |
| 滑动窗口推理 | 分块处理大尺寸3D图像 |

### 4.3 RAG检索流程

```
知识库文档
    │
    ▼
DocumentLoader → TextSplitter → Embeddings → ChromaDB
    │                │              │             │
    ▼                ▼              ▼             ▼
 加载文档         切分成块      生成向量       存储索引

查询 → Embeddings → Vector Search → 相似度排序 → Top-K结果
```

---

## 五、学习路径建议

### 5.1 入门阶段（1-2周）

1. **环境搭建**：安装依赖，运行 `python -m martin agent`
2. **基础概念**：理解三层架构、四个工具的功能
3. **单模块测试**：
   - 运行 `python -m martin detect -i test.nii.gz` 测试检测功能
   - 运行 `python -m martin case -i results/detection_results.json` 测试报告生成

### 5.2 进阶阶段（2-3周）

1. **深入代码**：
   - 阅读 `martin/agent/agent.py` 理解 Agent 执行流程
   - 阅读 `martin/llm/chain.py` 理解 LCEL 链编排
   - 阅读 `martin/rag/retriever.py` 理解 RAG 检索逻辑
2. **调试技巧**：
   - 查看 `log/agent_thinking/` 目录下的推理日志
   - 使用 `/list`、`/open` 命令查看会话历史

### 5.3 高级阶段（3-4周）

1. **扩展能力**：
   - 添加新工具（如风险评估、随访建议）
   - 接入新的大模型（如 GPT-4o、Claude 3）
   - 扩展知识库（添加更多医学指南）
2. **工程优化**：
   - 模型推理性能优化
   - 向量检索效率提升
   - 系统稳定性增强

---

## 六、常见问题

### Q1: 如何启动 Agent？

```bash
# 方式1：直接启动
python -m martin agent

# 方式2：启动时指定图像
python -m martin agent --image path/to/ct.nii.gz

# 方式3：使用根目录薄壳入口
python main.py
```

### Q2: 如何导入知识库？

```bash
python scripts/import_knowledge.py
```

### Q3: 检测结果保存在哪里？

默认保存在 `results/` 目录下，按日期分类。

### Q4: 会话历史如何持久化？

使用 LangGraph 官方 `SqliteSaver`，保存在 `data/sessions.sqlite`。

### Q5: 如何调试 Agent？

- 查看 `log/agent_thinking/YYYY-MM-DD.log` 查看完整推理过程
- 查看 `log/runtime/YYYY-MM-DD.log` 排查第三方 warning 和模型进度输出
- 使用 `/list` 查看历史会话

---

## 七、核心文件速查表

| 文件 | 功能 | 重要性 |
|------|------|--------|
| `martin/agent/agent.py` | Agent执行器 | ★★★★★ |
| `martin/agent/tools.py` | 工具定义 | ★★★★★ |
| `martin/agent/case_context.py` | 病例上下文 | ★★★★★ |
| `martin/agent/sessions.py` | 会话管理 | ★★★★☆ |
| `martin/llm/chain.py` | LCEL报告生成链 | ★★★★★ |
| `martin/llm/chat_model.py` | 大模型接口 | ★★★★☆ |
| `martin/rag/retriever.py` | 知识检索 | ★★★★☆ |
| `martin/rag/vector_store.py` | 向量存储 | ★★★☆☆ |
| `martin/vision/nodule_detector.py` | 结节检测 | ★★★★☆ |
| `martin/__main__.py` | 命令行入口 | ★★★☆☆ |

---

## 八、当前代码的完整调用关系

### 8.1 Agent 启动链

```text
python main.py
  -> main.py
  -> martin.__main__.handle_agent_v2()

python -m martin agent
  -> martin.__main__.main()
  -> argparse 选择 agent 子命令
  -> handle_agent_v2()

handle_agent_v2()
  -> AppLogger.disable_console_output()
  -> capture_runtime_output()              # 后台接收 warning / tqdm
  -> get_default_checkpointer()            # data/sessions.sqlite
  -> SessionManager(checkpointer)
  -> build_agent(thread_id, checkpointer)
  -> create_agent()
  -> AgentExecutor
```

### 8.2 一轮对话调用链

```text
AgentCLI.prompt()
  -> 普通中英文：AgentExecutor.invoke()
  -> / 开头命令：CLI 本地处理，不发送给 LLM

AgentExecutor.invoke()
  -> CaseContext.to_context_string()
  -> set_case_context(contextvars)
  -> LangGraph.invoke(messages, thread_id)
  -> DeepSeek 判断直接回答或调用工具
  -> _parse_result()
  -> _sync_case_context_from_steps()
  -> AgentCLI.assistant()
```

### 8.3 四条工具分支

| 分支 | 实际调用 | 状态变化 |
|------|----------|----------|
| CT 检测 | `analyze_image -> NoduleDetector.detect -> MONAI RetinaNet` | 更新 `CaseContext.image_info/nodules` |
| 医学检索 | `retrieve_knowledge -> search_by_query/search_by_detection -> ChromaDB` | 更新 `knowledge_summary` |
| 患者信息 | `update_case_context -> CaseContext.extract_patient_info` | 更新患者字段和临床备注 |
| 病例报告 | `generate_report tool -> llm.chain.generate_report -> LCEL -> DeepSeek` | 返回 Markdown；失败时模板降级 |

### 8.4 离线知识导入链

```text
scripts/import_knowledge.py
  -> configs/knowledge_base.yaml
  -> document_loader.load_knowledge_base()
  -> text_splitter.split_documents()
  -> embeddings.get_embeddings()
  -> vector_store.create_vector_store()
  -> ChromaDB/medical_knowledge
```

### 8.5 状态和输出位置

| 数据 | 路径/实现 | 重启后保留 |
|------|-----------|------------|
| 对话 checkpoint | `data/sessions.sqlite` | 是 |
| 结构化病例对象 | `AgentExecutor._context_cache` | 否 |
| 医学向量 | `ChromaDB/` | 是 |
| 检测和报告 | `results/` | 是 |
| 工具审计 | `audit/*.jsonl` | 是 |
| 应用日志 | `log/YYYY-MM-DD.log` | 是 |
| 推理日志 | `log/agent_thinking/` | 是 |
| 第三方运行输出 | `log/runtime/` | 是 |

---

## 九、项目文档地图

| 文档 | 定位 | 阅读顺序 |
|------|------|----------|
| `README.md` | 安装、启动、功能入口 | 第 1 个 |
| `docs/LEARNING_GUIDE.md` | 当前代码主学习文档和调用关系 | 第 2 个 |
| `docs/agent_flow.html` | 当前架构的可视化页面 | 配合学习指南 |
| `docs/ARCHITECTURE.md` | 模块边界、状态和数据流技术参考 | 第 3 个 |
| `docs/DEVELOPMENT.md` | 项目演进、技术决策、故障复盘 | 遇到设计问题时读 |
| `docs/LEARNING_SUMMARY.md` | 概念心得，不作为当前实现规范 | 最后阅读 |
| `docs/ROADMAP.md` | 未实现能力和技术债 | 规划开发时读 |
| `docs/CLEANUP_AUDIT.md` | 测试重复、假通过和清理候选 | 重构前阅读 |
| `PROJECT_ANALYSIS.md` | README 重构前的历史分析 | 仅作历史参考 |
| `knowledge_base/README.md` | 医学知识文件说明 | 学习 RAG 时读 |

文档描述和代码冲突时，以当前代码和自动测试为准。
