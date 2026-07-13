"""Agent 工具模块

提供四个 Agent 可直接调用的 LangChain Tool：
- analyze_image: 肺部CT图像结节检测分析
- retrieve_knowledge: 根据检测结果检索医学知识库
- generate_report: 生成结构化病例报告
- update_case_context: 根据用户输入更新病例上下文

使用方式:
    from martin.agent import (
        analyze_image,
        retrieve_knowledge,
        generate_report,
        update_case_context,
    )
"""

from martin.agent.agent_builder import build_agent
from martin.agent.tools import (
    analyze_image,
    generate_report,
    retrieve_knowledge,
    update_case_context,
)

__all__ = [
    "analyze_image",
    "retrieve_knowledge",
    "generate_report",
    "update_case_context",
    "build_agent",
]
