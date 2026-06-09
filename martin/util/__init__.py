"""
工具模块
提供通用工具类和函数
"""

from .logger import AppLogger
from .result_manager import ResultManager, get_result_manager

__all__ = ["AppLogger", "ResultManager", "get_result_manager"]
