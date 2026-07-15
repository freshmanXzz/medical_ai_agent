"""LangChain Embedding 封装模块

提供统一的 Embedding 模型加载与缓存管理功能。
底层使用 langchain_huggingface.HuggingFaceEmbeddings 加载 BGE 系列模型。
"""

import logging
import os

import torch
from langchain_huggingface import HuggingFaceEmbeddings

from martin.config import config

logger = logging.getLogger(__name__)

# 模块级缓存，避免重复加载模型
_embeddings: HuggingFaceEmbeddings | None = None


def get_embeddings(show_progress: bool = False) -> HuggingFaceEmbeddings:
    """获取 HuggingFace Embeddings 实例（带缓存）。

    首次调用时根据配置加载模型，后续调用复用缓存的实例。
    支持自动降级：
      - 本地模型路径不存在时，从 HuggingFace 在线加载
      - CUDA 不可用时自动回退到 CPU

    Args:
        show_progress: 是否显示进度条。默认关闭，避免污染交互式终端。

    Returns:
        HuggingFaceEmbeddings 实例。
    """
    global _embeddings

    if _embeddings is not None:
        return _embeddings

    # 确定设备
    device = config.embedding_device
    if device == "cuda" and not torch.cuda.is_available():
        logger.warning("CUDA 不可用，自动降级到 CPU")
        device = "cpu"

    # 确定模型路径/名称
    model_name_or_path = config.embedding_model_path
    if not os.path.exists(model_name_or_path):
        logger.info(
            "本地模型路径 '%s' 不存在，将从 HuggingFace 加载模型",
            model_name_or_path,
        )
        model_name_or_path = "BAAI/bge-small-zh-v1.5"

    logger.info("加载 Embedding 模型: %s (device: %s)", model_name_or_path, device)

    _embeddings = HuggingFaceEmbeddings(
        model_name=model_name_or_path,
        model_kwargs={"device": device},
        encode_kwargs={"normalize_embeddings": True},
        show_progress=show_progress,
    )
    return _embeddings


def clear_embeddings_cache() -> None:
    """清除 Embedding 模型缓存，强制下次调用时重新加载。"""
    global _embeddings
    _embeddings = None
    logger.info("Embedding 模型缓存已清除")
