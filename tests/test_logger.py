"""
测试日志工具类
"""
import json
import os
import sys
import logging
import tempfile
import pytest

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from martin.agent.audit import AuditLogger
from martin.utils import AppLogger


class TestAppLogger:
    """测试AppLogger类"""
    
    def test_logger_creation(self):
        """测试日志实例创建"""
        logger = AppLogger.setup_logging("test_logger")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "test_logger"
    
    def test_logger_singleton(self):
        """测试单例模式"""
        logger1 = AppLogger("test_singleton")
        logger2 = AppLogger("test_singleton")
        assert logger1 is logger2
    
    def test_logger_multiple_instances(self):
        """测试不同名称的日志实例"""
        logger1 = AppLogger("logger1")
        logger2 = AppLogger("logger2")
        assert logger1 is not logger2
    
    def test_log_levels(self):
        """测试日志级别"""
        logger = AppLogger.setup_logging("test_levels")
        
        # 这些应该不会抛出异常
        logger.debug("debug message")
        logger.info("info message")
        logger.warning("warning message")
        logger.error("error message")
        logger.critical("critical message")
    
    def test_log_file_creation(self):
        """测试日志文件创建"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            app_logger = AppLogger("test_file", log_dir=tmp_dir)
            logger = app_logger.get_logger()
            logger.info("test message")
            
            # 检查日志文件是否创建
            log_files = [f for f in os.listdir(tmp_dir) if f.endswith(".log")]
            assert len(log_files) == 1
            
            # 检查日志内容
            log_path = os.path.join(tmp_dir, log_files[0])
            with open(log_path, 'r', encoding='utf-8') as f:
                content = f.read()
                assert "test message" in content
            
            # 关闭文件处理器，避免 Windows 文件锁导致清理失败
            for handler in logger.handlers[:]:
                if isinstance(handler, logging.FileHandler):
                    handler.close()
                    logger.removeHandler(handler)
    
    def test_logger_methods(self):
        """测试日志方法"""
        logger = AppLogger.setup_logging("test_methods")
        
        # 测试各种日志方法
        logger.debug("debug")
        logger.info("info")
        logger.warning("warning")
        logger.error("error")
        logger.critical("critical")
        
        # 测试异常日志
        try:
            raise ValueError("test exception")
        except ValueError as e:
            logger.exception("exception occurred")
    
    def test_get_logger_function(self):
        """测试便捷函数"""
        from martin.utils.logger import get_logger

        logger = get_logger("test_function")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "test_function"


class TestAuditLogger:
    """测试 AuditLogger 类的审计日志功能"""

    def test_log_tool_call_with_user_input_and_final_output(self):
        """测试 log_tool_call 同时传入 user_input 和 final_output 时写入完整审计记录。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            audit_logger = AuditLogger(
                session_id="test_audit_full",
                audit_dir=tmp_dir,
            )
            audit_logger.log_tool_call(
                tool_name="retrieve_knowledge",
                args={
                    "query": "8mm结节",
                    "reasoning": "用户问 8mm 结节怎么办",
                },
                output_summary="Lung-RADS...",
                user_input="8mm结节怎么办",
                final_output="根据 Lung-RADS...",
            )

            with open(audit_logger.log_file, "r", encoding="utf-8") as f:
                record = json.loads(f.readline())

            assert record["user_input"] == "8mm结节怎么办"
            assert record["final_output"] == "根据 Lung-RADS..."
            assert record["reasoning"] == "用户问 8mm 结节怎么办"
            assert record["tool_name"] == "retrieve_knowledge"
            assert "reasoning" not in record["full_args"]

    def test_log_tool_call_backward_compatible(self):
        """测试 log_tool_call 不传 user_input/final_output 时使用默认空字符串。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            audit_logger = AuditLogger(
                session_id="test_audit_compat",
                audit_dir=tmp_dir,
            )
            audit_logger.log_tool_call(
                tool_name="analyze_image",
                args={"image_path": "x.nii.gz"},
                output_summary="检测到1个结节",
            )

            with open(audit_logger.log_file, "r", encoding="utf-8") as f:
                record = json.loads(f.readline())

            assert record["user_input"] == ""
            assert record["final_output"] == ""
            assert record["tool_name"] == "analyze_image"
            assert record["full_args"] == {"image_path": "x.nii.gz"}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
