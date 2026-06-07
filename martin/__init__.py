# 核心包初始化文件
# Martin - Medical AI Agent

__version__ = "0.1.0"
__author__ = "Martin"

# 导出核心模块
from .monai import *
from .llm import *
from .inference import LungNoduleDetector, detect_nodules

# 也可以通过 `from martin import LungNoduleDetector` 来导入
