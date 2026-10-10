"""Agent 审计日志模块

记录工具名称与执行状态；原始参数、思考文本和病历内容不进入审计文件。
"""

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


class AuditLogger:
    """记录最小执行元数据，临床来源由受权业务记录和记忆来源链保存。

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
        """保留旧调用接口，但不持久化自由文本，也不修改调用方参数。"""
        record = {
            "timestamp": datetime.now().isoformat(),
            "session_id": self.session_id,
            "tool_name": tool_name,
            "full_args": {},
            "reasoning": "",
            "output_summary": (
                "tool_failed"
                if str(output_summary).startswith("错误:")
                else "tool_completed"
            ),
            "user_input": "",
            "final_output": "",
        }

        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def log_agent_error(self, error_msg: str) -> None:
        """记录 Agent 执行错误。

        Args:
            error_msg: 错误信息。
        """
        record = {
            "timestamp": datetime.now().isoformat(),
            "session_id": self.session_id,
            "type": "error",
            "error": "agent_execution_failed",
        }
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
