"""Agent 编排与审计日志集成测试"""
import json
import os
import pytest
from unittest.mock import patch, MagicMock, PropertyMock


class TestAgentInitialization:
    """测试 Agent 初始化。"""

    def test_create_agent_with_default_tools(self):
        """测试使用默认工具创建 Agent。"""
        from martin.agent.agent import create_agent

        agent = create_agent(verbose=False)
        assert agent is not None
        assert len(agent.tools) == 4
        assert agent.handle_parsing_errors is True

    def test_agent_system_prompt_contains_reasoning(self):
        """测试 System Prompt 包含 reasoning 约束。"""
        from martin.agent.agent import SYSTEM_PROMPT

        assert "reasoning" in SYSTEM_PROMPT
        assert "推理" in SYSTEM_PROMPT
        assert "审计溯源" in SYSTEM_PROMPT
        assert "模拟专业医生的门诊沟通方式" in SYSTEM_PROMPT
        assert "中文和英文" in SYSTEM_PROMPT
        assert "你不是现实中的执业医生" in SYSTEM_PROMPT

    def test_report_prompt_does_not_invent_missing_imaging_features(self):
        from martin.llm.chain import SYS_PROMPT_DETAILED

        assert "世界坐标不得直接推断为肺叶位置" in SYS_PROMPT_DETAILED
        assert "当前资料无法分级" in SYS_PROMPT_DETAILED
        assert "不得虚构" in SYS_PROMPT_DETAILED

    def test_create_agent_tool_names(self):
        """测试工具名称正确。"""
        from martin.agent.agent import create_agent

        agent = create_agent(verbose=False)
        tool_names = [t.name for t in agent.tools]
        assert "analyze_image" in tool_names
        assert "retrieve_knowledge" in tool_names
        assert "generate_report" in tool_names
        assert "update_case_context" in tool_names


class TestAuditLogger:
    """测试审计日志模块。"""

    def test_audit_logger_creation(self):
        """测试审计日志创建。"""
        from martin.agent.audit import AuditLogger

        logger = AuditLogger(session_id="test_session")
        assert logger.session_id == "test_session"
        assert "audit" in logger.audit_dir

    def test_audit_log_tool_call_with_reasoning(self):
        """测试包含 reasoning 的审计日志记录。"""
        from martin.agent.audit import AuditLogger

        logger = AuditLogger(session_id="test_log")

        logger.log_tool_call(
            tool_name="analyze_image",
            args={
                "image_path": "test.nii.gz",
                "reasoning": "用户提供CT图像路径，需要分析",
            },
            output_summary="检测到2个结节",
        )

        # 验证日志文件存在且内容正确
        assert os.path.exists(logger.log_file)
        with open(logger.log_file, "r", encoding="utf-8") as f:
            record = json.loads(f.readline())

        assert record["tool_name"] == "analyze_image"
        assert record["reasoning"] == "用户提供CT图像路径，需要分析"
        assert "reasoning" not in record["full_args"]  # reasoning 已从 args 分离
        assert record["full_args"]["image_path"] == "test.nii.gz"

    def test_audit_log_missing_reasoning_warning(self):
        """测试 reasoning 缺失时记录警告。"""
        from martin.agent.audit import AuditLogger

        logger = AuditLogger(session_id="test_warn")

        # 不带 reasoning
        logger.log_tool_call(
            tool_name="test_tool",
            args={"key": "value"},
            output_summary="test output",
        )

        assert os.path.exists(logger.log_file)
        with open(logger.log_file, "r", encoding="utf-8") as f:
            record = json.loads(f.readline())

        assert record["reasoning"] == ""  # 空字符串

    def test_audit_log_error(self):
        """测试错误日志记录。"""
        from martin.agent.audit import AuditLogger

        logger = AuditLogger(session_id="test_err")
        logger.log_agent_error("LLM API 调用失败")

        with open(logger.log_file, "r", encoding="utf-8") as f:
            record = json.loads(f.readline())

        assert record["type"] == "error"
        assert "LLM API" in record["error"]


class TestCLIIntegration:
    """测试 CLI 集成。"""

    def test_agent_cli_help(self):
        """测试 agent 子命令的帮助信息。"""
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, "-m", "martin", "agent", "--help"],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        )
        assert "usage:" in result.stdout.lower()
        assert "--image" in result.stdout
        assert "--report-type" in result.stdout
        assert "--language" in result.stdout
