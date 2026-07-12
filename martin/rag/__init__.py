"""RAG 检索增强模块

基于 LangChain 框架实现的 RAG 组件：
- 文档加载与切分
- 向量嵌入
- 向量存储与检索
"""

from martin.rag.document_loader import load_knowledge_base, load_knowledge_directory
from martin.rag.text_splitter import split_documents
from martin.rag.embeddings import get_embeddings
from martin.rag.vector_store import create_vector_store, get_vector_store, get_retriever
from martin.rag.retriever import search_by_detection, format_results

__all__ = [
    "load_knowledge_base",
    "load_knowledge_directory",
    "split_documents",
    "get_embeddings",
    "create_vector_store",
    "get_vector_store",
    "get_retriever",
    "search_by_detection",
    "format_results",
]
