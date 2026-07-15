# Cleanup Audit — 测试与文件清理审计

> 审计日期：2026-07-15。本文只给出清理依据，不直接删除文件。

## 一、测试现状

- pytest 当前可收集 **111** 个测试。
- 快速单元测试主要集中在 Agent、Tools、CaseContext、CLI、日志和 SessionManager。
- 多个旧测试依赖本地 CT、GPU、Embedding、ChromaDB 或 API Key，缺少资源时存在“直接 return 但显示通过”的情况。

## 二、重复测试分组

| 分组 | 文件 | 结论 |
|------|------|------|
| 会话 | `test_session_persistence.py`、`test_sessions.py` | 前者 14 项已覆盖后者的最新 checkpoint、标题、消息过滤和 SQLite 重开；后者可合并后删除 |
| RAG/报告 | `test_integration.py`、`test_langchain_pipeline.py`、`test_rag_full_pipeline.py` | `test_langchain_pipeline.py` 断言最完整，建议作为主文件；其余改成显式 integration/manual 脚本 |
| 一键演示 | `test_one_click.py` | 6 个 `test_*` 函数但 0 个断言，且两个函数要求不存在的 `result` fixture；不应由 pytest 收集 |
| 结果管理 | `test_result_manager.py`、`test_one_click.py` | 都会写真实 `results/`；应改用 `tmp_path`，只保留 ResultManager 单元测试 |
| LLM | `test_llm.py`、`test_langchain_pipeline.py` | API Key 缺失时 `test_llm.py` 部分测试无断言直接通过；模型配置测试已在主 pipeline 覆盖 |
| MONAI | `test_monai.py`、`test_rag_full_pipeline.py`、`test_result_manager.py` | 都可能重复加载模型；应只保留一个带 `integration` 标记的真实推理测试 |

## 三、假通过风险

### 高风险

1. `tests/test_one_click.py`
   - 0 个断言。
   - `test_case_generator(result)` 和 `test_llm_generation(result)` 没有对应 fixture。
   - 建议移动为 `scripts/smoke_test.py`，并把函数名从 `test_*` 改为 `run_*`。

2. `tests/test_rag_full_pipeline.py`
   - 0 个断言。
   - CT 文件不存在时直接 `return`，pytest 会判定通过。
   - 质量检查只写日志，不会让失败反映到测试结果。

3. `tests/test_monai.py`
   - 模型初始化异常被捕获后仅打印 warning，测试仍可能通过。
   - 数据不存在时直接返回，应该使用 `pytest.skip()`。

### 中风险

- `tests/test_result_manager.py` 写入真实结果目录，测试之间会相互污染。
- `tests/test_integration.py` 自己重新实现文档加载和切分，没有验证生产 `document_loader/text_splitter`。
- `tests/test_llm.py` 根据环境变量分支，缺少 API Key 时部分测试没有有效断言。

## 四、推荐的目标测试结构

```text
tests/unit/
  test_agent.py
  test_tools.py
  test_case_context.py
  test_cli.py
  test_sessions.py
  test_rag_query.py
  test_report_templates.py
  test_logger.py

tests/integration/
  test_sqlite_checkpoint.py
  test_chroma_retrieval.py
  test_monai_inference.py
  test_llm_report.py

scripts/
  smoke_test.py
  manual_rag_pipeline.py
```

集成测试应统一使用 `@pytest.mark.integration`；缺少模型、数据或 API Key 时用 `pytest.skip()`，不能直接 `return`。

## 五、文件清理候选

### 可以在确认后删除或迁移

| 文件/符号 | 原因 | 建议 |
|-----------|------|------|
| `tests/test_one_click.py` | 实际是手工演示脚本 | 移到 `scripts/smoke_test.py` |
| `tests/test_rag_full_pipeline.py` | 无断言并写真实 results | 移到 `scripts/manual_rag_pipeline.py` 或重写 |
| `tests/test_sessions.py` | 与完整持久化测试重复 | 将必要快测并入主文件后删除 |
| `PROJECT_ANALYSIS.md` | 与 README、Architecture、Learning Guide 重复且含旧 MemorySaver | 移到 `docs/archive/` 或删除 |
| `handle_agent_legacy()` | 当前没有入口调用 | 删除前确认不再支持旧 CLI |
| `create_memory_checkpointer()` | 生产代码和测试均未调用 | 删除或仅保留为测试 fixture |
| `get_retriever_for_detection()` | 仓库内无调用 | 删除前确认没有外部 API 使用者 |

### 必须保留

- `main.py`：虽然很薄，但它是用户常用的快捷入口。
- `docs/case_report_demo.png`：README 正在引用。
- `docs/session_history_demo.svg`：README 正在引用。
- `scripts/import_knowledge.py`：ChromaDB 不会自动初始化，必须显式导入。
- `data/sessions.sqlite`、`ChromaDB/`、`results/`、`audit/`、`log/`：属于运行数据，应保持 gitignore，不提交。

### 不应自动处理

- 仓库根目录未跟踪的个人简历 PDF 与项目无关且可能包含隐私。应由文件所有者确认后移出项目；自动化工具不应读取、提交或删除。
- `models/` 和 CT 数据体积大且不入 Git，但本地运行依赖它们，不能当作垃圾文件删除。

## 六、建议执行顺序

1. 先修复知识库乱码文件名，确认可以从零重建 ChromaDB。
2. 修正 `test_one_click.py` 的 pytest 收集问题。
3. 合并两个 Session 测试文件。
4. 给真实 GPU/RAG/LLM 测试增加 `integration` marker。
5. 把所有测试输出改到 `tmp_path`。
6. 再删除死代码和归档 `PROJECT_ANALYSIS.md`。
7. 最后运行快速测试与显式 integration 测试，确认覆盖没有下降。

## 七、审计中发现的非重复问题

### 7.1 知识库文件名编码损坏

`configs/knowledge_base.yaml` 期望以下正常文件名：

- `01_肺叶分段解剖图示.md`
- `04_CT肺结节诊断专家共识2023.md`
- `05_肺结节诊疗指南2024.md`

当前工作区对应文件名显示为乱码，`load_knowledge_base()` 会提示文件不存在。已有 `ChromaDB/` 数据会暂时掩盖问题，但在新机器或清空向量库后无法完整重建。修复时应使用 Git 级重命名，并核对文件内容编码，不能只修改 YAML。

### 7.2 两份依赖清单不一致

- `requirements.txt` 包含生产代码实际使用的 `langchain-chroma`、`langchain-huggingface`、`sentence-transformers`、`pyyaml`、`pypdf`、`python-docx`。
- `pyproject.toml` 缺少上述依赖，执行 `pip install -e .` 后可能无法运行完整 RAG。
- `requirements.txt` 中的 `psycopg2-binary` 和 `pgvector` 在当前代码中没有引用，属于旧方案遗留候选。
- `matplotlib` 当前生产代码没有引用，如无单独可视化脚本也可移除。

建议选择 `pyproject.toml` 作为唯一依赖源，`requirements.txt` 由锁定/导出流程生成，避免人工维护两份列表。
