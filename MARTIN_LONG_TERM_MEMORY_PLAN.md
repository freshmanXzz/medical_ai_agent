# Martin 长期记忆架构实施计划

## 目标

在当前 `refactor/memory-auth-v1` 基础上，把 Martin 的长期记忆明确拆成三种检索方式：

```text
确定事实      → 精确检索
模糊经验/讨论 → 语义向量检索
时间演变      → 时间事件链检索
```

所有检索必须先经过：

```text
doctor / patient / case 身份范围
→ 权限校验
→ 再进行具体记忆检索
```

不要把所有历史内容统一向量化，也不要把长期记忆和医学知识 RAG 混成一个库。

---

# Phase 0：先审查当前项目，不修改代码

先完整检查当前分支：

```text
refactor/memory-auth-v1
```

重点阅读并梳理：

```text
martin/
api/
tests/
scripts/
docs/refactor/
```

同时检查当前所有数据库、表、关系、Store namespace、Saver 配置和 RAG 实现。

至少确认：

```text
Business DB
- users
- patients
- cases
- threads
- doctor_patient_access
- findings
- reports
- attachments
- auth/session
- audit 相关表

Memory
- SqliteStore 初始化方式
- namespace 设计
- MemoryService
- 当前写入/读取入口
- doctor preference
- patient memory
- case memory

Saver
- SqliteSaver
- thread_id 与业务 Thread 的关系

RAG
- BGE embedding
- Chroma / vector store
- 当前知识库 collection
```

同时检查表之间的：

```text
主键
外键
级联规则
唯一约束
时间字段
source_id / finding_id / case_id
doctor_id / patient_id / thread_id
```

先输出一份：

```text
CURRENT_MEMORY_ARCHITECTURE_AUDIT.md
```

内容至少包括：

```text
1. 当前数据库表和关系
2. 当前 SqliteStore namespace
3. 当前记忆读写链路
4. 当前 Prompt 注入链路
5. 当前 RAG 向量链路
6. 哪些信息已经结构化
7. 哪些信息适合增加语义记忆
8. 哪些信息需要时间事件链
9. 现有设计与本计划冲突点
```

**Phase 0 完成前不要开始改业务代码。**

---

# Phase 1：先完成当前 V1.1

当前已知未完成项：

```text
A. Doctor Preference
Store 检索成功
Prompt 注入成功
真实 LLM 遵循不稳定

C. Store Failure Degradation
Store 读取失败时当前会提前 503
```

先修完这两项。

不要改已经通过的：

```text
Patient longitudinal memory
6mm → 8mm
```

完成后重新跑：

```text
offline tests
live LLM acceptance
full regression
```

V1.1 通过后再进入新的长期记忆架构扩展。

---

# Phase 2：给长期记忆建立统一分类

Martin 长期记忆按“内容类型”分类：

| Memory Type           | 内容           | 主检索方式            |
| --------------------- | ------------ | ---------------- |
| doctor_preference     | 报告格式、长度、关注重点 | 精确检索             |
| workflow_preference   | 医生分析/操作习惯    | 精确检索，必要时语义       |
| patient_fact          | 患者稳定事实       | Business DB 精确检索 |
| medical_observation   | 结节大小、部位、征象等  | 精确 + 时间          |
| clinical_decision     | 为什么随访/进一步检查等 | 语义 + 时间          |
| case_evolution        | 6mm→8mm、征象变化 | 时间事件链            |
| historical_discussion | 过去病例讨论、推理背景  | 语义向量             |
| task_followup         | 复查、等待结果、下次比较 | 精确 + 时间          |
| correction            | 用户明确纠正的信息    | 精确，必要时语义         |

每条长期记忆必须保留来源信息，例如：

```text
memory_id
memory_type

doctor_id
patient_id
case_id
thread_id

source_type
source_id

created_at
observed_at

status
confidence
```

不要让 Memory 成为 Business DB 的第二个事实源。

---

# Phase 3：实现三种检索器

## A. Exact Retriever

负责：

```text
doctor preference
workflow preference
patient facts
corrections
tasks
明确 finding
```

优先使用：

```text
Business DB SQL
SqliteStore namespace + key
metadata filter
```

能精确查询的信息禁止优先走向量 Top-K。

---

## B. Temporal Retriever

负责病例的纵向变化。

至少支持：

```text
patient_id
finding type
body location
observed_at
case_id
source_finding_id
```

典型查询：

```text
“上次结节多大？”
“半年内有什么变化？”
“和当前 8mm 相比呢？”
```

返回结果必须能形成：

```text
2026-06  6mm
    ↓
2026-09  8mm
    ↓
change = +2mm
```

时间关系由结构化数据确定，不允许让 LLM 自己从语义片段猜测。

---

## C. Semantic Retriever

负责：

```text
clinical decision
historical discussion
难以固定字段表示的医生经验/上下文
```

流程：

```text
当前用户问题
↓
embedding
↓
限定 doctor / patient / case scope
↓
vector Top-K
↓
metadata/time filter
↓
rerank
```

可以复用现有 BGE embedding 能力，但：

**医学知识 RAG 和长期记忆 Vector Memory 必须逻辑隔离。**

例如：

```text
Knowledge RAG
→ 医学指南、知识库

Memory Vector Search
→ 医生/患者/病例历史
```

不得在同一 collection 中混查。

在实现前先确认当前 LangGraph Store 版本是否已支持需要的语义搜索能力；如果不满足，再设计独立 Memory Vector Index。

---

# Phase 4：Memory Retrieval Router

新增统一的 Retrieval Router。

输入至少包含：

```text
doctor_id
patient_id
case_id
thread_id
current user query
```

执行顺序：

```text
用户问题
↓
身份确认
↓
权限校验
↓
Query Intent / Retrieval Plan
├── Exact Retriever
├── Temporal Retriever
└── Semantic Retriever
↓
结果合并
↓
去重
↓
来源标注
↓
重要性/相关性排序
↓
Memory Context
↓
Prompt
```

允许一次问题同时调用多个 Retriever。

例如：

```text
“这个患者为什么上次选择观察，现在又有什么变化？”
```

应该同时：

```text
Temporal
→ 查 6mm → 8mm

Semantic
→ 查上次“为什么继续观察”的 clinical decision
```

最后再合并给 LLM。

---

# Phase 5：Memory Writer

不要直接把整段聊天全部写入长期记忆。

先从一次交互中识别：

```text
是否存在值得长期保存的信息
↓
属于哪种 memory_type
↓
是否已有同一事实
↓
新增 / 更新 / supersede
```

例如：

```text
医生：
“这个患者之前 6mm，没有明显毛刺，继续观察。
以后报告结论写前面一点。”
```

拆成：

```text
medical_observation
- 6mm
- 无明显毛刺

clinical_decision
- 继续观察

doctor_preference
- conclusion_first = true
```

分别保存。

医疗事实仍以 Business DB 为 source of truth。

---

# Phase 6：测试

至少增加以下场景：

```text
Exact
- 医生偏好跨 Thread
- correction 精确召回
- 不依赖向量也能稳定命中

Temporal
- 6mm → 8mm
- 多次随访按时间正确排序
- historical/current 不混淆
- superseded fact 不作为当前事实

Semantic
- “之前为什么选择观察？”
- “以前讨论过类似情况吗？”
- 同一患者相关记忆能召回
- 不相关记忆不进入 Top-K

Isolation
- D001 不读取 D002 私有记忆
- 无患者权限的医生不能做患者向量检索
- 不跨 patient 串记忆

RAG Separation
- Memory Vector 不返回医学知识文档
- Knowledge RAG 不返回患者私有记忆

Failure
- Semantic index 失败时 Exact/Temporal 仍可工作
- Store 读取失败时当前病例分析可继续
- 不伪造历史
```

---

# Phase 7：验收标准

最终必须能证明：

```text
明确事实
→ Exact Retriever

纵向变化
→ Temporal Retriever

模糊历史讨论/决策
→ Semantic Retriever
```

并且：

```text
Authorization
→ Scope
→ Retrieval
→ Merge
→ Prompt
→ LLM
```

链路清晰可测试。

最后输出：

```text
MEMORY_ARCHITECTURE_IMPLEMENTATION_REPORT.md
```

包括：

```text
Current architecture audit
Schema / namespace changes
Retriever implementation
Memory Router
Memory Writer
Vector index design
Tests
Full regression
Live LLM acceptance
Known limitations
Next step
```

---

# 约束

本轮不要做：

```text
PostgreSQL migration
PostgresStore / PostgresSaver
复杂 memory consolidation
自动遗忘策略
跨患者全局语义搜索
大规模 reranker
```

先把：

```text
Exact + Temporal + Semantic
```

三类长期记忆检索在当前 SQLite / LangGraph 架构上做清楚、做稳定。
