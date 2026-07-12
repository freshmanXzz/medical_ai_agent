# 核心包初始化文件
# Martin - Medical AI Agent

__version__ = "0.1.0"
__author__ = "Martin"

# 导出核心模块
from .vision import *
from .llm import *
from .inference import LungNoduleDetector, detect_nodules

# 导出 RAG 组件
from .rag import (
    load_knowledge_base,
    load_knowledge_directory,
    split_documents,
    get_embeddings,
    create_vector_store,
    get_vector_store,
    get_retriever,
    search_by_detection,
    format_results,
)

# 导出配置
from .config import LangChainConfig, config
