"""MinIO OSS 对象存储客户端模块

封装 MinIO SDK，提供单例客户端与文件上传/下载能力。
供 API 路由和 Agent 工具调用，实现影像文件的远程存储与获取。
"""

import logging
import os
import tempfile
import uuid
from pathlib import Path
from typing import Optional

from minio import Minio
from minio.error import S3Error

from martin.config import config

logger = logging.getLogger(__name__)

# 模块级单例缓存
_client_instance: Optional["MinioClient"] = None


def is_oss_path(path: str) -> bool:
    """判断输入路径是 OSS 对象路径还是本地文件路径。

    支持以下 OSS 路径格式：
    - oss://bucket/object_name
    - MinIO 默认 ``ct/`` 前缀下的纯对象名（如 ct/sample.nii.gz）

    Args:
        path: 输入路径字符串。

    Returns:
        True 表示 OSS 路径，False 表示本地路径。
    """
    if not path:
        return False

    # oss:// 前缀直接判定为 OSS 路径
    if path.startswith("oss://"):
        return True

    # 本地文件存在则视为本地路径
    if os.path.isfile(path):
        return False

    # Unix 绝对路径（/开头）或 Windows 盘符路径（含:）视为本地路径
    if path.startswith("/") or ":" in path:
        return False

    # 上传接口默认产生 ct/<uuid> 路径。其他相对路径应优先视为项目内的
    # 本地路径，避免 data/not-found.nii.gz 这类输入在 MinIO 不可用时被误报
    # 为服务端错误，而不是清晰的 404。
    return path.replace("\\", "/").startswith("ct/")


def parse_oss_path(path: str) -> tuple:
    """解析 OSS 路径，返回 (bucket, object_name)。

    Args:
        path: OSS 路径，如 oss://bucket/object 或纯对象名。

    Returns:
        (bucket, object_name) 元组。若路径中未指定 bucket，返回 (None, object_name)。
    """
    if path.startswith("oss://"):
        stripped = path[len("oss://"):]
        parts = stripped.split("/", 1)
        if len(parts) == 2:
            return parts[0], parts[1]
        return parts[0], ""
    return None, path


class MinioClient:
    """MinIO 客户端封装类。

    使用单例模式，首次实例化时创建 Minio 连接并确保 bucket 存在。
    """

    def __init__(self):
        self._client = Minio(
            endpoint=config.minio_endpoint,
            access_key=config.minio_access_key,
            secret_key=config.minio_secret_key,
            secure=config.minio_secure,
        )
        self._bucket = config.minio_bucket_name
        self._bucket_ready = False

    def ensure_bucket(self) -> None:
        """确保配置的 bucket 存在，不存在则自动创建。"""
        if self._bucket_ready:
            return

        try:
            if not self._client.bucket_exists(self._bucket):
                self._client.make_bucket(self._bucket)
                logger.info("已自动创建 bucket: %s", self._bucket)
            self._bucket_ready = True
        except S3Error as e:
            logger.error("确保 bucket 存在失败: %s", e)
            raise

    def upload_file(self, local_path: str, object_name: str = "") -> str:
        """上传本地文件到 OSS。

        Args:
            local_path: 本地文件路径。
            object_name: OSS 对象名，为空时自动生成。

        Returns:
            上传后的对象名。
        """
        self.ensure_bucket()

        if not object_name:
            ext = Path(local_path).suffix
            if local_path.endswith(".nii.gz"):
                ext = ".nii.gz"
            object_name = f"ct/{uuid.uuid4().hex}{ext}"

        file_size = os.path.getsize(local_path)
        content_type = "application/octet-stream"

        self._client.fput_object(
            bucket_name=self._bucket,
            object_name=object_name,
            file_path=local_path,
            content_type=content_type,
        )
        logger.info(
            "文件已上传到 OSS: %s/%s, 大小: %d bytes",
            self._bucket,
            object_name,
            file_size,
        )
        return object_name

    def download_file(self, object_name: str, local_path: str = "") -> str:
        """从 OSS 下载文件到本地。

        Args:
            object_name: OSS 对象名。
            local_path: 本地保存路径，为空时使用临时目录。

        Returns:
            下载后的本地文件路径。
        """
        self.ensure_bucket()

        if not local_path:
            # 根据对象名扩展名生成临时文件
            ext = Path(object_name).suffix
            if object_name.endswith(".nii.gz"):
                ext = ".nii.gz"
            tmp_fd, local_path = tempfile.mkstemp(suffix=ext)
            os.close(tmp_fd)

        self._client.fget_object(
            bucket_name=self._bucket,
            object_name=object_name,
            file_path=local_path,
        )
        logger.info(
            "文件已从 OSS 下载: %s/%s → %s",
            self._bucket,
            object_name,
            local_path,
        )
        return local_path

    @property
    def bucket(self) -> str:
        """返回当前配置的 bucket 名称。"""
        return self._bucket


def get_oss_client() -> MinioClient:
    """获取 MinioClient 单例实例。

    首次调用时创建实例并缓存，后续调用直接返回缓存实例。

    Returns:
        MinioClient 实例。
    """
    global _client_instance
    if _client_instance is None:
        _client_instance = MinioClient()
    return _client_instance
