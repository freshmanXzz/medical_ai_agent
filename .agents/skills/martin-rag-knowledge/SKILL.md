---
name: martin-rag-knowledge
description: 维护 Martin 知识库文档、加载器、中文编码、Chroma 向量库、检索结果、来源引用或知识管理界面时使用；适用于 martin/rag、knowledge_base、API 和测试修改。
---

# Martin RAG Knowledge

## 工作流

1. 先确认配置列出的每份资料在 `knowledge_base/` 中存在、文件名匹配且可按正确编码读取。
2. 再检查 loader、chunking、embedding、Chroma 存储和 `retrieve_knowledge` 的调用端；重建前保留运行时索引数据的风险提示。
3. 为资料数量、来源 metadata、检索结果与界面展示补充或更新测试。

## 不可破坏的契约

- 知识库重建不得静默跳过资料。预期来源数与实际加载数不一致时必须显式失败或告警。
- CSV 不得默认假定 GBK；使用 UTF-8 或安全编码探测。中文文件名、配置和 metadata 必须一致。
- 返回给 Agent/报告的每条证据保留可展示的来源；空检索结果必须明确表达“当前资料未覆盖”。
- 不把外部通用知识伪装为本项目检索结果；知识管理页的测试检索不能影响线上索引。

## 验证

优先运行 RAG loader、检索和完整管线测试；Python 验证遵循 `AGENTS.md`。参考 `docs/DEVELOPMENT.md` 和 `docs/ARCHITECTURE.md`。
