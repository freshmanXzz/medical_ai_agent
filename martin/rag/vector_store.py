"""LangChain Chroma 向量数据库封装模块

提供向量库的创建、获取、检索功能，统一管理 Chroma 持久化操作。
"""

import logging
import os

try:
    from langchain_chroma import Chroma
except ImportError:
    Chroma = None  # type: ignore

from martin.config import config

logger = logging.getLogger(__name__)

# 模块级缓存，避免重复创建 Chroma 实例
_vector_store: Chroma | None = None


def create_vector_store(documents, embeddings, collection_name=None):
    """创建新的向量库并对文档建立索引。

    如果指定集合已存在，则先删除再重建，避免数据污染。

    Args:
        documents: 待索引的文档列表（List[Document]）。
        embeddings: Embedding 模型实例。
        collection_name: 集合名称，默认为 config.chroma_collection_name。

    Returns:
        Chroma 实例。
    """
    global _vector_store

    if Chroma is None:
        raise ImportError(
            "langchain_chroma 未安装，请执行: pip install langchain-chroma"
        )

    persist_dir = config.chroma_persist_dir
    collection = collection_name or config.chroma_collection_name

    # 如果集合已存在，删除重建
    try:
        existing = Chroma(
            persist_directory=persist_dir,
            embedding_function=embeddings,
            collection_name=collection,
        )
        existing.delete_collection()
        logger.info("已删除已有的集合 '%s'", collection)
    except Exception as exc:
        logger.warning("删除已有集合时发生异常: %s", exc)

    _vector_store = Chroma.from_documents(
        documents=documents,
        embedding=embeddings,
        persist_directory=persist_dir,
        collection_name=collection,
    )
    logger.info(
        "向量库创建完成，持久化路径: %s，集合: %s", persist_dir, collection
    )
    return _vector_store


def get_vector_store(embeddings=None, collection_name=None):
    """获取已有的向量库实例。

    检查持久化目录是否存在且包含 chroma.sqlite3 数据库文件。
    如果未提供 embeddings，则自动通过 get_embeddings() 获取。

    Args:
        embeddings: Embedding 模型实例（可选）。未提供时自动加载。
        collection_name: 集合名称，默认为 config.chroma_collection_name。

    Returns:
        如果存在则返回 Chroma 实例，否则返回 None。
    """
    global _vector_store

    if _vector_store is not None:
        return _vector_store

    if Chroma is None:
        raise ImportError(
            "langchain_chroma 未安装，请执行: pip install langchain-chroma"
        )

    # 自动获取 embeddings（如果未提供）
    if embeddings is None:
        from martin.rag.embeddings import get_embeddings
        embeddings = get_embeddings()

    persist_dir = config.chroma_persist_dir
    sqlite_path = os.path.join(persist_dir, "chroma.sqlite3")

    # 检查持久化目录是否存在且包含数据库文件
    if not os.path.isdir(persist_dir) or not os.path.isfile(sqlite_path):
        logger.info(
            "向量库持久化目录不存在或未找到 chroma.sqlite3: %s", persist_dir
        )
        return None

    collection = collection_name or config.chroma_collection_name
    _vector_store = Chroma(
        persist_directory=persist_dir,
        embedding_function=embeddings,
        collection_name=collection,
    )
    logger.info("已加载已有向量库，持久化路径: %s，集合: %s", persist_dir, collection)
    return _vector_store


def get_retriever(vector_store, top_k=None):
    """从 VectorStore 获取 VectorStoreRetriever。

    Args:
        vector_store: Chroma 向量库实例。
        top_k: 检索返回的最相关文档数，默认为 config.top_k（默认 5）。

    Returns:
        VectorStoreRetriever 实例。
    """
    k = top_k if top_k is not None else config.top_k
    return vector_store.as_retriever(
        search_type="similarity",
        search_kwargs={"k": k},
    )


def add_documents(documents, document_id: str):
    """向默认集合增量加入某份知识文档的切分结果。"""
    global _vector_store
    if Chroma is None:
        raise ImportError("langchain_chroma 未安装，请执行: pip install langchain-chroma")

    from martin.rag.embeddings import get_embeddings

    if _vector_store is None:
        _vector_store = Chroma(
            persist_directory=config.chroma_persist_dir,
            embedding_function=get_embeddings(),
            collection_name=config.chroma_collection_name,
        )
    ids = [f"{document_id}:{index}" for index in range(len(documents))]
    _vector_store.add_documents(documents, ids=ids)
    return len(ids)


def delete_document_vectors(document_id: str) -> None:
    """删除指定文档写入的所有向量。"""
    global _vector_store
    store = _vector_store or get_vector_store()
    if store is not None:
        store._collection.delete(where={"document_id": document_id})


def reset_vector_store_cache() -> None:
    """在删除或整库重建后使下一次检索重新打开 Chroma 集合。"""
    global _vector_store
    _vector_store = None
