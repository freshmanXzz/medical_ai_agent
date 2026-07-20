"""LangChain 统一配置模块

集中管理所有 LangChain 组件的配置参数，包括：
- ChromaDB 持久化路径
- Embedding 模型路径
- DeepSeek LLM 配置
- 文本切分和检索参数
"""

import os
from pathlib import Path
from typing import Optional


class LangChainConfig:
    """LangChain 配置类，统一管理所有组件参数。

    配置加载优先级：环境变量 > 默认值
    """

    def __init__(self):
        # 项目根目录 (martin/ -> 项目根)
        self._project_root: Optional[Path] = None

    @property
    def project_root(self) -> Path:
        """获取项目根目录路径。"""
        if self._project_root is None:
            current = Path(__file__).resolve().parent  # martin/
            self._project_root = current.parent  # 项目根
        return self._project_root

    # ─── ChromaDB ───────────────────────────────────────────
    @property
    def chroma_persist_dir(self) -> str:
        """ChromaDB 持久化目录路径。"""
        return os.environ.get(
            "CHROMA_PERSIST_DIR",
            str(self.project_root / "ChromaDB"),
        )

    @property
    def chroma_collection_name(self) -> str:
        """ChromaDB 集合名称。"""
        return os.environ.get("CHROMA_COLLECTION", "medical_knowledge")

    # ─── Embedding ──────────────────────────────────────────
    @property
    def embedding_model_path(self) -> str:
        """本地 Embedding 模型路径。"""
        return os.environ.get(
            "EMBEDDING_MODEL_PATH",
            str(self.project_root / "models" / "embedding" / "bge-small-zh-v1.5"),
        )

    @property
    def embedding_dimension(self) -> int:
        """Embedding 向量维度。"""
        return int(os.environ.get("EMBEDDING_DIMENSION", "512"))

    @property
    def embedding_device(self) -> str:
        """Embedding 模型运行设备。"""
        return os.environ.get("EMBEDDING_DEVICE", "cuda")

    # ─── DeepSeek ───────────────────────────────────────────
    @property
    def deepseek_api_key(self) -> Optional[str]:
        """DeepSeek API 密钥。"""
        return os.environ.get("DEEPSEEK_API_KEY")

    @property
    def deepseek_base_url(self) -> str:
        """DeepSeek API 基础地址。"""
        return os.environ.get(
            "DEEPSEEK_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        )

    @property
    def deepseek_model(self) -> str:
        """DeepSeek 模型名称。"""
        return os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro")

    # ─── MinIO OSS ───────────────────────────────────────────
    @property
    def minio_endpoint(self) -> str:
        """MinIO 服务地址（host:port）。"""
        return os.environ.get("MINIO_ENDPOINT", "localhost:9000")

    @property
    def minio_access_key(self) -> str:
        """MinIO 访问密钥。"""
        return os.environ.get("MINIO_ACCESS_KEY", "minioadmin")

    @property
    def minio_secret_key(self) -> str:
        """MinIO 秘密密钥。"""
        return os.environ.get("MINIO_SECRET_KEY", "minioadmin")

    @property
    def minio_bucket_name(self) -> str:
        """MinIO 默认 bucket 名称。"""
        return os.environ.get("MINIO_BUCKET", "martin-medical")

    @property
    def minio_secure(self) -> bool:
        """是否使用 HTTPS 连接 MinIO。"""
        return os.environ.get("MINIO_SECURE", "false").lower() == "true"

    # ─── 文本切分 ────────────────────────────────────────────
    @property
    def chunk_size(self) -> int:
        """文本切分块大小（字符数）。"""
        return int(os.environ.get("CHUNK_SIZE", "500"))

    @property
    def chunk_overlap(self) -> int:
        """文本切分块重叠大小（字符数）。"""
        return int(os.environ.get("CHUNK_OVERLAP", "50"))

    # ─── 检索 ───────────────────────────────────────────────
    @property
    def top_k(self) -> int:
        """检索返回的最相关文档数。"""
        return int(os.environ.get("RETRIEVER_TOP_K", "5"))

    @property
    def similarity_threshold(self) -> float:
        """检索相似度阈值（低于此值的文档被过滤）。"""
        return float(os.environ.get("RETRIEVER_THRESHOLD", "0.7"))


# 全局单例
config = LangChainConfig()
