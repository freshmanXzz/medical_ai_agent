---
name: martin-reporting
description: 维护 Martin 影像报告提示词、报告类型、报告 API、CaseContext 输入、知识依据、失败降级或报告工作台时使用；适用于 martin/llm/chain.py、报告工具和测试修改。
---

# Martin Reporting

## 工作流

1. 先确认输入来自当前检测结果或已恢复的 `CaseContext`，再修改提示词、模板或 API；不要复制一套独立病例状态。
2. 检查 brief、detailed、research 三种报告及知识检索失败时的降级结果。
3. 涉及医学判断时同时加载 `martin-agent-policy` 和 `martin-rag-knowledge`。

## 不可破坏的契约

- 报告只能使用输入中存在的患者、检查、结节和知识资料字段；缺失的密度、肺叶、边缘、钙化或生长信息必须明确为缺失。
- 世界坐标不能推断肺叶位置；资料不足不能强行给出 Lung-RADS 类别、确诊结论或伪精确随访建议。
- 引用必须可追溯到当前知识资料；没有资料时生成基础报告并说明局限性，而不是编造引用。
- 历史会话只要有已保存结节，即使是旧数据，也应能重建报告输入并继续生成报告。

## 验证

运行报告链、工具和历史会话恢复的相关测试；检查 Markdown 输出、三种类型、空知识和 LLM 失败降级。Python 验证遵循 `AGENTS.md`。
