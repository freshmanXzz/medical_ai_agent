"""LLM 推理模块

基于 LangChain 和 DeepSeek 实现的 LLM 组件：
- ChatModel 封装
- 报告生成链
- 病例报告生成器
- DeepSeek 客户端
"""

from martin.llm.deepseek_client import DeepSeekClient
from martin.llm.case_generator import CaseGenerator
from martin.llm.chat_model import get_chat_model
from martin.llm.chain import generate_report

__all__ = ["DeepSeekClient", "CaseGenerator", "get_chat_model", "generate_report"]
