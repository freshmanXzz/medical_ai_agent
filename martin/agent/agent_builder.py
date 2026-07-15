"""Agent 构建工厂模块

提供 build_agent() 函数，串联 LLM/Tools/Prompt/Memory/Logger
的初始化流程，返回可直接使用的 AgentExecutor 实例。

使用方式:
    from martin.agent.agent_builder import build_agent
    agent = build_agent(verbose=True, thread_id="session-001")
"""

import logging
from typing import Optional

from langgraph.checkpoint.base import BaseCheckpointSaver

logger = logging.getLogger(__name__)


def build_agent(
    verbose: bool = True,
    thread_id: Optional[str] = None,
    checkpointer: Optional[BaseCheckpointSaver] = None,
):
    """构建完整的 Agent 执行器。

    按顺序完成以下初始化：
    1. 加载 LLM — 调用 get_chat_model()，验证 LLM 可用性
    2. 加载 Tools — 由 create_agent() 内部默认加载三个核心工具
    3. 加载 Prompt — 由 create_agent() 内部使用 SYSTEM_PROMPT
    4. 加载 Memory — 使用传入或默认的 LangGraph SqliteSaver
    5. 加载 Logger — verbose=True 启用 AgentLoggingHandler
    6. 创建 AgentExecutor — 调用 create_agent()

    Args:
        verbose: 是否打印详细思维日志。默认 True。
        thread_id: 会话 ID。同一 thread_id 的多次调用共享记忆。
                  默认 None（使用 "default"）。

    Returns:
        配置好的 AgentExecutor 实例。

    Raises:
        ValueError: LLM 初始化失败（如 API Key 未配置）。
    """
    # 惰性导入以避免与 __init__.py 之间的循环依赖
    from martin.agent.agent import create_agent
    from martin.llm.chat_model import get_chat_model

    # Step 1: 验证 LLM 可用性（提前失败，避免构建 Agent 后再报错）
    try:
        llm = get_chat_model()
        # 通过简单调用来验证 LLM 是否真正可用
        # 注意：get_chat_model() 可能不会立即失败
    except Exception as e:
        error_msg = f"模型初始化失败，请检查配置: {e}"
        logger.error(error_msg)
        raise ValueError(error_msg) from e

    logger.info("LLM 加载成功")

    # Step 2-6: 构建 Agent（内部完成 Tools/Prompt/Memory/Logger 的加载）
    try:
        agent_executor = create_agent(
            verbose=verbose,
            thread_id=thread_id,
            checkpointer=checkpointer,
        )
        logger.info("Agent 构建成功, thread_id=%s", thread_id or "default")
        return agent_executor
    except Exception as e:
        error_msg = f"Agent 构建失败: {e}"
        logger.error(error_msg, exc_info=True)
        raise ValueError(error_msg) from e
