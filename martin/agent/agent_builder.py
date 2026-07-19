"""Agent 构建工厂模块

提供 build_agent() 函数，作为 create_agent() 的薄封装，
统一异常处理与日志输出，供 CLI 入口使用。

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

    直接委托 create_agent()，由其内部完成：
    1. 加载 LLM — AgentExecutor.__init__ 调用 get_chat_model()
    2. 加载 Tools — 默认加载六个核心工具
    3. 加载 Prompt — 使用 SYSTEM_PROMPT
    4. 加载 Memory — 使用传入或默认的 LangGraph SqliteSaver
    5. 加载 Logger — verbose=True 启用 AgentLoggingHandler

    Args:
        verbose: 是否打印详细思维日志。默认 True。
        thread_id: 会话 ID。同一 thread_id 的多次调用共享记忆。
                  默认 None（使用 "default"）。
        checkpointer: 可选的检查点保存器，默认 None 时使用 SqliteSaver。

    Returns:
        配置好的 AgentExecutor 实例。

    Raises:
        ValueError: Agent 构建失败（如 LLM API Key 未配置）。
    """
    # 惰性导入以避免与 __init__.py 之间的循环依赖
    from martin.agent.agent import create_agent

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
