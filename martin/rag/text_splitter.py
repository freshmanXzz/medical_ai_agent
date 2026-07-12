"""LangChain 文本切分器封装模块

提供基于 RecursiveCharacterTextSplitter 的文档切分功能，
支持中文文本优化分隔符顺序。
"""

from typing import List

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

from martin.config import config


def split_documents(documents: List[Document]) -> List[Document]:
    """使用 RecursiveCharacterTextSplitter 切分文档列表。

    针对中文文本优化了分隔符顺序（在默认分隔符列表开头添加"。"和"；"），
    并在切分后的每个 Document 的 metadata 中添加 chunk_index 字段记录块序号。

    Args:
        documents: 待切分的文档列表

    Returns:
        切分后的文档列表，每个文档保留原始 metadata 并包含 chunk_index
    """
    # 中文优化分隔符：将中文句号、分号置于首位
    separators = ["。", "；", "\n\n", "\n", " ", ""]

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.chunk_size,
        chunk_overlap=config.chunk_overlap,
        separators=separators,
    )

    chunks = text_splitter.split_documents(documents)

    # 为每个切分块添加序号
    for index, chunk in enumerate(chunks):
        chunk.metadata["chunk_index"] = index

    return chunks
