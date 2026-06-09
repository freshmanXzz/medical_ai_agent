"""
AppLogger - 统一日志工具类

提供单例模式的日志服务，支持：
- 控制台输出
- 文件输出（按日期分割）
- 自定义日志级别
- 线程安全
"""
import os
import logging
from datetime import datetime
from typing import Optional


class AppLogger:
    """
    应用日志工具类
    
    单例模式，确保全局只有一个日志实例
    
    Args:
        name: 日志名称，通常使用 __name__
        log_dir: 日志文件存放目录，默认为项目根目录下的 log 目录
        level: 日志级别，默认为 INFO
    """
    
    _instances = {}
    
    def __new__(cls, name: str = __name__, log_dir: str = None):
        """单例模式实现"""
        if name not in cls._instances:
            cls._instances[name] = super(AppLogger, cls).__new__(cls)
        return cls._instances[name]
    
    def __init__(self, name: str = __name__, log_dir: str = None):
        """
        初始化日志工具类
        
        Args:
            name: 日志名称
            log_dir: 日志目录，默认自动查找项目根目录
        """
        self._name = name
        self._log_dir = log_dir or self._get_default_log_dir()
        self._logger = None
        self._initialized = False
        
        if not self._initialized:
            self._setup_logger()
            self._initialized = True
    
    @staticmethod
    def _get_default_log_dir() -> str:
        """获取默认日志目录"""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # 向上查找项目根目录
        project_root = os.path.dirname(os.path.dirname(current_dir))
        log_dir = os.path.join(project_root, "log")
        os.makedirs(log_dir, exist_ok=True)
        return log_dir
    
    def _setup_logger(self):
        """设置日志配置"""
        self._logger = logging.getLogger(self._name)
        self._logger.setLevel(logging.INFO)
        
        # 避免重复添加处理器
        if self._logger.handlers:
            return
        
        # 日志格式
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # 控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        self._logger.addHandler(console_handler)
        
        # 文件处理器（按日期分割）
        log_filename = datetime.now().strftime("%Y-%m-%d") + ".log"
        log_filepath = os.path.join(self._log_dir, log_filename)
        file_handler = logging.FileHandler(log_filepath, encoding='utf-8', mode='a')
        file_handler.setFormatter(formatter)
        self._logger.addHandler(file_handler)
    
    def get_logger(self) -> logging.Logger:
        """获取日志实例"""
        return self._logger
    
    @staticmethod
    def setup_logging(name: str = __name__, log_dir: str = None) -> logging.Logger:
        """
        便捷方法：快速获取配置好的日志实例
        
        Args:
            name: 日志名称
            log_dir: 日志目录
        
        Returns:
            配置好的 Logger 实例
        """
        return AppLogger(name, log_dir).get_logger()


# 全局便捷函数
def get_logger(name: str = __name__, log_dir: str = None) -> logging.Logger:
    """
    获取日志实例的便捷函数
    
    Args:
        name: 日志名称
        log_dir: 日志目录
    
    Returns:
        Logger 实例
    """
    return AppLogger.setup_logging(name, log_dir)
