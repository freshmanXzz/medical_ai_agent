"""Agent 审计日志模块

拦截 Agent 中间步骤，提取工具调用中的 reasoning 字段并持久化到 JSONL 文件。
"""
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


class AuditLogger:
    """审计日志记录器，记录 Agent 工具调用的 reasoning 字段用于医疗审计溯源。

    Args:
        session_id: 会话 ID，默认为自动生成的 UUID。
        audit_dir: 审计日志目录，默认为项目根目录下的 audit/。
    """

    def __init__(
        self,
        session_id: Optional[str] = None,
        audit_dir: Optional[str] = None,
    ):
        self.session_id = session_id or str(uuid4())[:8]
        # 审计日志目录：默认在项目根目录的 audit/ 下
        if audit_dir is None:
            # 相对于当前文件的路径计算：martin/agent/audit.py -> 项目根
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(os.path.dirname(current_dir))  # martin/ -> 项目根
            audit_dir = os.path.join(project_root, "audit")
        self.audit_dir = audit_dir
        os.makedirs(self.audit_dir, exist_ok=True)

        # 日志文件路径：audit/{session_id}_{timestamp}.jsonl
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = os.path.join(
            self.audit_dir, f"{self.session_id}_{timestamp}.jsonl"
        )
        logger.info("审计日志文件: %s", self.log_file)

    def log_tool_call(
        self,
        tool_name: str,
        args: Dict[str, Any],
        output_summary: str,
        user_input: str = "",
        final_output: str = "",
    ) -> None:
        """记录一次工具调用。

        从 args 中提取 reasoning 字段，与其他信息一起写入 JSONL 文件。

        Args:
            tool_name: 工具名称。
            args: 工具调用的完整参数。
            output_summary: 工具输出的摘要（前 500 字符）。
            user_input: 用户原始输入，用于审计溯源（前 500 字符）。
            final_output: Agent 最终回答摘要，用于审计溯源（前 500 字符）。
        """
        reasoning = args.pop("reasoning", "") if isinstance(args, dict) else ""
        record = {
            "timestamp": datetime.now().isoformat(),
            "session_id": self.session_id,
            "tool_name": tool_name,
            "full_args": args,  # 不包含 reasoning（已 pop）
            "reasoning": reasoning,
            "output_summary": output_summary[:500],
            "user_input": user_input[:500],  # 用户原始输入（截断到 500 字符）
            "final_output": final_output[:500],  # Agent 最终回答摘要（截断到 500 字符）
        }

        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        if not reasoning:
            logger.warning(
                "审计日志警告: 工具 %s 的 reasoning 字段缺失", tool_name
            )

    def log_agent_error(self, error_msg: str) -> None:
        """记录 Agent 执行错误。

        Args:
            error_msg: 错误信息。
        """
        record = {
            "timestamp": datetime.now().isoformat(),
            "session_id": self.session_id,
            "type": "error",
            "error": error_msg,
        }
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
