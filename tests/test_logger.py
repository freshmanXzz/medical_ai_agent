"""
测试日志工具类
"""
import os
import sys
import logging
import tempfile
import pytest

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from martin.util import AppLogger


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
            logger = AppLogger("test_file", log_dir=tmp_dir).get_logger()
            logger.info("test message")
            
            # 检查日志文件是否创建
            log_files = [f for f in os.listdir(tmp_dir) if f.endswith(".log")]
            assert len(log_files) == 1
            
            # 检查日志内容
            log_path = os.path.join(tmp_dir, log_files[0])
            with open(log_path, 'r', encoding='utf-8') as f:
                content = f.read()
                assert "test message" in content
    
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
        from martin.util.logger import get_logger
        
        logger = get_logger("test_function")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "test_function"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
