"""
VectorStore - 向量数据库客户端
使用 ChromaDB 存储和检索医学知识向量（轻量级，无需Docker）
"""

import os
from typing import Any, Dict, List, Optional

import chromadb
from chromadb.config import Settings

# 导入统一日志工具
from martin.util import AppLogger

logger = AppLogger.setup_logging(__name__)

# 常量定义
DEFAULT_COLLECTION_NAME = "medical_knowledge"
EMBEDDING_DIMENSION = 512


class VectorStore:
    """
    向量数据库客户端

    使用ChromaDB存储和检索医学知识向量（轻量级解决方案）

    Args:
        persist_directory: 向量数据库持久化目录
        collection_name: 集合名称
    """

    def __init__(
        self,
        persist_directory: str = None,
        collection_name: str = DEFAULT_COLLECTION_NAME,
    ):
        """
        初始化向量数据库客户端

        参数优先级：传入参数 > 环境变量 > 默认值
        """
        self.persist_directory = persist_directory or os.environ.get(
            "CHROMA_PERSIST_DIR", "ChromaDB"
        )
        self.collection_name = collection_name
        self._client = None
        self._collection = None

        logger.info(
            f"VectorStore 初始化: persist_dir={self.persist_directory}, collection={self.collection_name}"
        )

    def connect(self) -> bool:
        """
        连接数据库

        Returns:
            连接成功返回 True，失败返回 False
        """
        try:
            # 创建持久化客户端
            self._client = chromadb.PersistentClient(
                path=self.persist_directory,
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True,
                ),
            )

            # 获取或创建集合
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name, metadata={"dimension": EMBEDDING_DIMENSION}
            )

            logger.info(f"ChromaDB 连接成功，集合: {self.collection_name}")
            return True
        except Exception as e:
            logger.error(f"ChromaDB 连接失败: {e}")
            return False

    def disconnect(self):
        """断开数据库连接（ChromaDB无需显式断开）"""
        self._client = None
        self._collection = None
        logger.info("ChromaDB 连接已关闭")

    def _ensure_connection(self):
        """确保数据库连接有效"""
        if not self._client or not self._collection:
            if not self.connect():
                raise ConnectionError("无法连接到 ChromaDB")

    def insert_chunks(
        self,
        contents: List[str],
        embeddings: List[List[float]],
        sources: List[str],
        categories: List[str] = None,
        metadata: List[Dict] = None,
    ) -> int:
        """
        批量插入向量数据

        Args:
            contents: 文本内容列表
            embeddings: 向量列表
            sources: 来源列表
            categories: 分类列表（可选）
            metadata: 元数据列表（可选）

        Returns:
            插入的记录数

        Raises:
            ValueError: 参数长度不匹配
        """
        if not contents or not embeddings or not sources:
            raise ValueError("contents, embeddings, sources 不能为空")

        if len(contents) != len(embeddings) or len(contents) != len(sources):
            raise ValueError("contents, embeddings, sources 长度必须一致")

        self._ensure_connection()

        # 准备元数据
        metadatas = []
        for i in range(len(contents)):
            meta = {
                "source": sources[i],
                "chunk_index": i,
            }
            if categories:
                meta["category"] = categories[i]
            if metadata:
                meta["extra"] = str(metadata[i])
            metadatas.append(meta)

        # 生成唯一ID
        ids = [f"chunk_{sources[i]}_{i}" for i in range(len(contents))]

        try:
            # 批量添加
            self._collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=contents,
                metadatas=metadatas,
            )

            logger.info(f"成功插入 {len(contents)} 条向量记录")
            return len(contents)

        except Exception as e:
            logger.error(f"插入向量数据失败: {e}")
            raise

    def similarity_search(
        self, query_embedding: List[float], top_k: int = 5, category: str = None
    ) -> List[Dict]:
        """
        相似度检索

        Args:
            query_embedding: 查询向量
            top_k: 返回结果数量，默认 5
            category: 过滤分类（可选）

        Returns:
            检索结果列表，每项包含 content, source, similarity, category
        """
        self._ensure_connection()

        try:
            # 构建查询条件
            where_filter = {"category": category} if category else None

            # 执行查询
            results = self._collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=where_filter,
                include=["documents", "metadatas", "distances"],
            )

            # 格式化结果（ChromaDB使用余弦距离，范围[0,2]，标准化到[0,1]相似度）
            formatted_results = []
            if results and results["documents"]:
                for i in range(len(results["documents"][0])):
                    meta = results["metadatas"][0][i]
                    # 余弦距离标准化：distance=0表示完全相同，distance=2表示完全相反
                    # 相似度 = 1 - distance/2，范围[0, 1]
                    distance = results["distances"][0][i]
                    similarity = max(0.0, min(1.0, 1.0 - distance / 2.0))
                    formatted_results.append(
                        {
                            "content": results["documents"][0][i],
                            "source": meta.get("source", ""),
                            "category": meta.get("category", ""),
                            "similarity": similarity,
                            "distance": distance,
                        }
                    )

            logger.info(f"相似度检索返回 {len(formatted_results)} 条结果")
            return formatted_results

        except Exception as e:
            logger.error(f"相似度检索失败: {e}")
            raise

    def clear_table(self) -> int:
        """
        清空向量表

        Returns:
            删除的记录数
        """
        self._ensure_connection()

        try:
            count = self._collection.count()
            self._collection.delete(where={})

            logger.info(f"已清空向量表，删除 {count} 条记录")
            return count

        except Exception as e:
            logger.error(f"清空向量表失败: {e}")
            raise

    def get_chunk_count(self) -> int:
        """
        获取向量数量

        Returns:
            向量表中的记录数
        """
        self._ensure_connection()
        return self._collection.count()

    def reset(self):
        """
        重置数据库（删除所有数据）
        """
        self._ensure_connection()
        self._client.delete_collection(self.collection_name)
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name, metadata={"dimension": EMBEDDING_DIMENSION}
        )
        logger.info("ChromaDB 已重置")

    def __enter__(self):
        """上下文管理器入口"""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.disconnect()
        return False
