"""Agent 工具模块

提供六个 Agent 可直接调用的 LangChain Tool：
- analyze_image: 肺部CT图像结节检测分析（支持本地路径和 OSS 对象名）
- retrieve_knowledge: 根据检测结果检索医学知识库
- generate_report: 生成结构化病例报告
- update_case_context: 根据用户输入更新病例上下文
- upload_to_oss: 将本地文件上传到 OSS 对象存储
- download_from_oss: 从 OSS 下载文件到本地临时目录

使用方式:
    from martin.agent import (
        analyze_image,
        retrieve_knowledge,
        generate_report,
        update_case_context,
        upload_to_oss,
        download_from_oss,
    )
"""

from martin.agent.agent_builder import build_agent
from martin.agent.tools import (
    analyze_image,
    download_from_oss,
    generate_report,
    retrieve_knowledge,
    update_case_context,
    upload_to_oss,
)

__all__ = [
    "analyze_image",
    "retrieve_knowledge",
    "generate_report",
    "update_case_context",
    "upload_to_oss",
    "download_from_oss",
    "build_agent",
]
