"""
ResultManager - 结果文件管理工具类

提供按日期分类的结果文件管理功能：
- 自动创建日期目录
- 自动生成带时间戳的文件名
- 支持检测结果和报告文件的保存
"""
import os
import json
from datetime import datetime
from typing import Dict, Optional


class ResultManager:
    """
    结果文件管理器
    
    功能：
    - 按日期自动分类存储
    - 自动生成带时间戳的文件名
    - 支持检测结果和报告文件
    
    Args:
        base_dir: 结果文件基础目录，默认为项目根目录下的 results
    """
    
    def __init__(self, base_dir: str = None):
        self._base_dir = base_dir or self._get_default_base_dir()
    
    @staticmethod
    def _get_default_base_dir() -> str:
        """获取默认结果目录"""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(current_dir))
        return os.path.join(project_root, "results")
    
    def get_date_dir(self, date_str: str = None) -> str:
        """
        获取指定日期的目录，不存在则创建
        
        Args:
            date_str: 日期字符串，格式 YYYY-MM-DD，默认为当天
        
        Returns:
            日期目录的绝对路径
        """
        if date_str is None:
            date_str = datetime.now().strftime("%Y-%m-%d")
        
        date_dir = os.path.join(self._base_dir, date_str)
        os.makedirs(date_dir, exist_ok=True)
        return date_dir
    
    def get_today_dir(self) -> str:
        """
        获取今天的目录
        
        Returns:
            今天日期目录的绝对路径
        """
        return self.get_date_dir()
    
    def generate_filename(
        self,
        prefix: str,
        extension: str,
        timestamp: bool = True
    ) -> str:
        """
        生成文件名
        
        Args:
            prefix: 文件名前缀
            extension: 文件扩展名（包含点，如 .json）
            timestamp: 是否添加时间戳
        
        Returns:
            格式化的文件名
        """
        if timestamp:
            time_str = datetime.now().strftime("%H%M%S")
            return f"{prefix}_{time_str}{extension}"
        return f"{prefix}{extension}"
    
    def save_detection_result(
        self,
        result: Dict,
        filename: str = None,
        date_str: str = None
    ) -> str:
        """
        保存检测结果到日期目录
        
        Args:
            result: 检测结果字典
            filename: 文件名，默认自动生成
            date_str: 日期字符串，默认今天
        
        Returns:
            保存的文件路径
        """
        date_dir = self.get_date_dir(date_str)
        
        if filename is None:
            image_name = result.get("image", "unknown")
            safe_name = os.path.splitext(image_name)[0]
            timestamp = datetime.now().strftime("%H%M%S")
            filename = f"detection_{safe_name}_{timestamp}.json"
        
        filepath = os.path.join(date_dir, filename)
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=4, ensure_ascii=False)
        
        return filepath
    
    def save_report(
        self,
        report: str,
        filename: str = None,
        date_str: str = None
    ) -> str:
        """
        保存报告到日期目录
        
        Args:
            report: 报告内容
            filename: 文件名，默认自动生成
            date_str: 日期字符串，默认今天
        
        Returns:
            保存的文件路径
        """
        date_dir = self.get_date_dir(date_str)
        
        if filename is None:
            timestamp = datetime.now().strftime("%H%M%S")
            filename = f"case_report_{timestamp}.md"
        
        filepath = os.path.join(date_dir, filename)
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(report)
        
        return filepath
    
    def get_latest_dir(self) -> str:
        """
        获取最新的结果目录（按日期排序）
        
        Returns:
            最新日期目录路径，如果不存在则创建今天的目录
        """
        if not os.path.exists(self._base_dir):
            return self.get_today_dir()
        
        dirs = [
            d for d in os.listdir(self._base_dir)
            if os.path.isdir(os.path.join(self._base_dir, d))
        ]
        
        if not dirs:
            return self.get_today_dir()
        
        latest = sorted(dirs, reverse=True)[0]
        return os.path.join(self._base_dir, latest)
    
    def list_results(self, date_str: str = None) -> list:
        """
        列出指定日期的结果文件
        
        Args:
            date_str: 日期字符串，默认今天
        
        Returns:
            结果文件路径列表
        """
        date_dir = self.get_date_dir(date_str)
        
        if not os.path.exists(date_dir):
            return []
        
        files = []
        for filename in os.listdir(date_dir):
            filepath = os.path.join(date_dir, filename)
            if os.path.isfile(filepath):
                files.append(filepath)
        
        return sorted(files)
    
    def load_detection_result(self, filepath: str) -> Dict:
        """
        加载检测结果文件
        
        Args:
            filepath: 结果文件路径
        
        Returns:
            检测结果字典
        """
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)


# 全局便捷函数
def get_result_manager(base_dir: str = None) -> ResultManager:
    """
    获取结果管理器实例
    
    Args:
        base_dir: 结果目录路径
    
    Returns:
        ResultManager 实例
    """
    return ResultManager(base_dir)
