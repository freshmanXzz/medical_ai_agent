"""Martin Medical Agent — 终端启动入口

使用方式:
    python main.py

本文件只负责用户交互，Agent 构建由 agent_builder.py 完成。
"""

import logging
import sys

from martin.agent.agent_builder import build_agent
from martin.agent.audit import AuditLogger

# 配置根日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


BANNER = """
================================
      Martin Medical Agent
      医学智能体已启动

  输入 exit 退出对话
================================
"""


def chat_loop(agent, audit_logger):
    """对话循环：读取用户输入 -> Agent 处理 -> 输出结果。

    Args:
        agent: AgentExecutor 实例。
        audit_logger: AuditLogger 实例，用于记录审计日志。
    """
    print("User: ", end="", flush=True)
    for line in sys.stdin:
        # 去除首尾空白
        user_input = line.strip()

        # 空输入跳过
        if not user_input:
            print("User: ", end="", flush=True)
            continue

        # 退出命令
        if user_input.lower() in ("exit", "quit", "退出"):
            print("Martin: 再见！")
            break

        # 调用 Agent
        try:
            response = agent.invoke({"input": user_input})
            output = response.get("output", "")
            if output:
                print(f"Martin: {output}")
            else:
                print("Martin: 抱歉，我没有生成有效的回应。")
        except Exception as e:
            error_msg = f"工具执行异常: {e}"
            logger.error(error_msg, exc_info=True)
            print(f"Martin: {error_msg}")
            if audit_logger:
                audit_logger.log_agent_error(error_msg)

        # 审计日志记录中间步骤
        if audit_logger:
            try:
                for step in response.get("intermediate_steps", []):
                    action, result = step
                    audit_logger.log_tool_call(
                        tool_name=action.tool,
                        args=action.tool_input,
                        output_summary=str(result)[:500],
                    )
            except Exception as e:
                logger.warning("审计日志记录失败: %s", e)

        print()
        print("User: ", end="", flush=True)


def main():
    """主入口：初始化 Agent 并启动对话循环。"""
    print(BANNER)

    # Step 1: 构建 Agent（所有组件由 build_agent 内部完成）
    try:
        agent = build_agent(verbose=True)
    except ValueError as e:
        print(f"Martin: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Martin: 未知错误: {e}")
        sys.exit(1)

    # Step 2: 创建审计日志记录器
    try:
        audit_logger = AuditLogger()
    except Exception as e:
        logger.warning("审计日志初始化失败: %s", e)
        audit_logger = None

    print("Martin: 您好！我是 Martin 医学智能体，可以为您提供医学影像分析和知识查询服务。")
    print()

    # Step 3: 启动对话循环
    try:
        chat_loop(agent, audit_logger)
    except KeyboardInterrupt:
        print("\nMartin: 再见！")
        sys.exit(0)
    except Exception as e:
        logger.error("对话循环异常: %s", e, exc_info=True)
        print(f"Martin: 对话出现异常: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
