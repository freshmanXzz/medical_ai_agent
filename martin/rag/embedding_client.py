"""
EmbeddingClient - 本地向量嵌入客户端
使用 BAAI/bge-small-zh-v1.5 模型进行文本向量化
"""

import os
from typing import List, Optional

import numpy as np
from sentence_transformers import SentenceTransformer

# 设置HuggingFace镜像源（中国大陆加速）
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

# 导入统一日志工具
from martin.util import AppLogger

logger = AppLogger.setup_logging(__name__)

# 常量定义
DEFAULT_MODEL_PATH = "models/bge-small-zh-v1.5"
EMBEDDING_DIMENSION = 512
MAX_SEQ_LENGTH = 512


class EmbeddingClient:
    """
    本地Embedding客户端

    使用BAAI/bge-small-zh-v1.5模型进行中文文本向量化

    Args:
        model_path: 模型路径，默认为 models/bge-small-zh-v1.5
    """

    def __init__(self, model_path: Optional[str] = None):
        """
        初始化Embedding客户端

        Args:
            model_path: 模型路径，默认为 models/bge-small-zh-v1.5
        """
        self.model_path = model_path or DEFAULT_MODEL_PATH
        self._model = None

        # 获取项目根目录
        project_root = self._get_project_root()
        full_model_path = os.path.join(project_root, self.model_path)

        logger.info(f"正在加载Embedding模型: {full_model_path}")

        try:
            # 尝试从本地加载模型
            if os.path.exists(full_model_path):
                self._model = SentenceTransformer(full_model_path)
                logger.info("从本地加载Embedding模型成功")
            else:
                raise FileNotFoundError(f"模型路径不存在: {full_model_path}")
        except Exception as e:
            # 如果本地加载失败，尝试从HuggingFace下载
            logger.warning(f"本地模型加载失败: {e}")
            logger.info("尝试从HuggingFace下载模型: BAAI/bge-small-zh-v1.5")
            self._model = SentenceTransformer("BAAI/bge-small-zh-v1.5")
            logger.info("从HuggingFace下载Embedding模型成功")

        self._model.max_seq_length = MAX_SEQ_LENGTH
        logger.info("Embedding模型加载完成")

    @staticmethod
    def _get_project_root() -> str:
        """获取项目根目录"""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # martin/rag/embedding_client.py -> 向上两级到项目根目录
        return os.path.dirname(os.path.dirname(current_dir))

    def encode(self, texts: List[str]) -> np.ndarray:
        """
        向量化文本列表

        Args:
            texts: 文本列表

        Returns:
            向量数组，形状为 (len(texts), 512)
        """
        if not texts:
            return np.array([])

        logger.debug(f"开始向量化 {len(texts)} 条文本")
        embeddings = self._model.encode(
            texts, normalize_embeddings=True, show_progress_bar=False
        )
        logger.debug(f"向量化完成，输出形状: {embeddings.shape}")
        return embeddings

    def encode_single(self, text: str) -> np.ndarray:
        """
        向量化单个文本

        Args:
            text: 文本内容

        Returns:
            向量数组，形状为 (512,)
        """
        if not text:
            return np.zeros(EMBEDDING_DIMENSION)

        embedding = self._model.encode(
            text, normalize_embeddings=True, show_progress_bar=False
        )
        return embedding

    def get_embedding_dimension(self) -> int:
        """
        获取向量维度

        Returns:
            向量维度，固定为512
        """
        return EMBEDDING_DIMENSION
