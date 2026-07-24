"""OSS 客户端模块单元测试

覆盖 is_oss_path、parse_oss_path 路径判断函数，
以及 MinioClient 的 upload_file、download_file、ensure_bucket 方法（使用 mock）。
"""
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from martin.utils.oss_client import is_oss_path, parse_oss_path


class TestIsOssPath:
    """测试 is_oss_path 路径判断函数。"""

    def test_oss_protocol_prefix(self):
        """oss:// 前缀直接判定为 OSS 路径。"""
        assert is_oss_path("oss://martin-medical/ct/sample.nii.gz") is True

    def test_oss_protocol_prefix_no_object(self):
        """oss:// 前缀即使没有对象名也返回 True。"""
        assert is_oss_path("oss://martin-medical") is True

    def test_local_existing_file(self):
        """本地存在的文件视为本地路径。"""
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".nii.gz")
        try:
            os.write(tmp_fd, b"dummy")
            os.close(tmp_fd)
            assert is_oss_path(tmp_path) is False
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_relative_ct_object_name(self):
        """默认 ct/ 前缀下的对象名视为 OSS 路径。"""
        assert is_oss_path("ct/sample.nii.gz") is True

    def test_missing_relative_local_path_is_not_oss(self):
        """缺失的项目相对路径仍应由本地路径校验返回 404。"""
        assert is_oss_path("data/not-present.nii.gz") is False

    def test_absolute_local_path_not_exist(self):
        """绝对路径且本地不存在时视为非 OSS 路径。"""
        assert is_oss_path("/nonexistent/absolute/path.nii.gz") is False

    def test_windows_absolute_path(self):
        """Windows 盘符路径视为本地路径。"""
        assert is_oss_path("C:/data/ct/sample.nii.gz") is False

    def test_empty_string(self):
        """空字符串返回 False。"""
        assert is_oss_path("") is False

    def test_none_like_input(self):
        """None 输入返回 False。"""
        assert is_oss_path(None) is False


class TestParseOssPath:
    """测试 parse_oss_path 路径解析函数。"""

    def test_full_oss_path(self):
        """解析完整的 oss://bucket/object 路径。"""
        bucket, obj = parse_oss_path("oss://martin-medical/ct/sample.nii.gz")
        assert bucket == "martin-medical"
        assert obj == "ct/sample.nii.gz"

    def test_oss_path_bucket_only(self):
        """解析仅含 bucket 的 oss:// 路径。"""
        bucket, obj = parse_oss_path("oss://martin-medical")
        assert bucket == "martin-medical"
        assert obj == ""

    def test_plain_object_name(self):
        """纯对象名返回 (None, object_name)。"""
        bucket, obj = parse_oss_path("ct/sample.nii.gz")
        assert bucket is None
        assert obj == "ct/sample.nii.gz"


class TestMinioClient:
    """测试 MinioClient 类（使用 mock 避免真实 MinIO 连接）。"""

    @patch("martin.utils.oss_client.Minio")
    @patch("martin.utils.oss_client.config")
    def test_ensure_bucket_creates_when_not_exists(self, mock_config, mock_minio_class):
        """bucket 不存在时自动创建。"""
        mock_config.minio_endpoint = "localhost:9000"
        mock_config.minio_access_key = "minioadmin"
        mock_config.minio_secret_key = "minioadmin"
        mock_config.minio_bucket_name = "test-bucket"
        mock_config.minio_secure = False

        mock_client = MagicMock()
        mock_client.bucket_exists.return_value = False
        mock_minio_class.return_value = mock_client

        from martin.utils.oss_client import MinioClient

        client = MinioClient()
        client.ensure_bucket()

        mock_client.bucket_exists.assert_called_once_with("test-bucket")
        mock_client.make_bucket.assert_called_once_with("test-bucket")

    @patch("martin.utils.oss_client.Minio")
    @patch("martin.utils.oss_client.config")
    def test_ensure_bucket_skips_when_exists(self, mock_config, mock_minio_class):
        """bucket 已存在时不重复创建。"""
        mock_config.minio_endpoint = "localhost:9000"
        mock_config.minio_access_key = "minioadmin"
        mock_config.minio_secret_key = "minioadmin"
        mock_config.minio_bucket_name = "test-bucket"
        mock_config.minio_secure = False

        mock_client = MagicMock()
        mock_client.bucket_exists.return_value = True
        mock_minio_class.return_value = mock_client

        from martin.utils.oss_client import MinioClient

        client = MinioClient()
        client.ensure_bucket()

        mock_client.bucket_exists.assert_called_once_with("test-bucket")
        mock_client.make_bucket.assert_not_called()

    @patch("martin.utils.oss_client.Minio")
    @patch("martin.utils.oss_client.config")
    def test_upload_file_success(self, mock_config, mock_minio_class):
        """上传文件成功并返回对象名。"""
        mock_config.minio_endpoint = "localhost:9000"
        mock_config.minio_access_key = "minioadmin"
        mock_config.minio_secret_key = "minioadmin"
        mock_config.minio_bucket_name = "test-bucket"
        mock_config.minio_secure = False

        mock_client = MagicMock()
        mock_client.bucket_exists.return_value = True
        mock_minio_class.return_value = mock_client

        # 创建临时测试文件
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".nii.gz")
        try:
            os.write(tmp_fd, b"dummy content")
            os.close(tmp_fd)

            from martin.utils.oss_client import MinioClient

            client = MinioClient()
            result = client.upload_file(tmp_path, "ct/test-upload.nii.gz")

            assert result == "ct/test-upload.nii.gz"
            mock_client.fput_object.assert_called_once()
            call_kwargs = mock_client.fput_object.call_args
            assert call_kwargs.kwargs["bucket_name"] == "test-bucket"
            assert call_kwargs.kwargs["object_name"] == "ct/test-upload.nii.gz"
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    @patch("martin.utils.oss_client.Minio")
    @patch("martin.utils.oss_client.config")
    def test_upload_file_auto_generate_object_name(self, mock_config, mock_minio_class):
        """未指定 object_name 时自动生成。"""
        mock_config.minio_endpoint = "localhost:9000"
        mock_config.minio_access_key = "minioadmin"
        mock_config.minio_secret_key = "minioadmin"
        mock_config.minio_bucket_name = "test-bucket"
        mock_config.minio_secure = False

        mock_client = MagicMock()
        mock_client.bucket_exists.return_value = True
        mock_minio_class.return_value = mock_client

        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".nii.gz")
        try:
            os.write(tmp_fd, b"dummy")
            os.close(tmp_fd)

            from martin.utils.oss_client import MinioClient

            client = MinioClient()
            result = client.upload_file(tmp_path)

            # 自动生成的对象名以 ct/ 开头，以 .nii.gz 结尾
            assert result.startswith("ct/")
            assert result.endswith(".nii.gz")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    @patch("martin.utils.oss_client.Minio")
    @patch("martin.utils.oss_client.config")
    def test_download_file_to_specified_path(self, mock_config, mock_minio_class):
        """下载文件到指定路径。"""
        mock_config.minio_endpoint = "localhost:9000"
        mock_config.minio_access_key = "minioadmin"
        mock_config.minio_secret_key = "minioadmin"
        mock_config.minio_bucket_name = "test-bucket"
        mock_config.minio_secure = False

        mock_client = MagicMock()
        mock_client.bucket_exists.return_value = True
        mock_minio_class.return_value = mock_client

        from martin.utils.oss_client import MinioClient

        client = MinioClient()
        result = client.download_file("ct/sample.nii.gz", "/tmp/downloaded.nii.gz")

        assert result == "/tmp/downloaded.nii.gz"
        mock_client.fget_object.assert_called_once_with(
            bucket_name="test-bucket",
            object_name="ct/sample.nii.gz",
            file_path="/tmp/downloaded.nii.gz",
        )

    @patch("martin.utils.oss_client.Minio")
    @patch("martin.utils.oss_client.config")
    def test_download_file_to_temp(self, mock_config, mock_minio_class):
        """未指定本地路径时下载到临时目录。"""
        mock_config.minio_endpoint = "localhost:9000"
        mock_config.minio_access_key = "minioadmin"
        mock_config.minio_secret_key = "minioadmin"
        mock_config.minio_bucket_name = "test-bucket"
        mock_config.minio_secure = False

        mock_client = MagicMock()
        mock_client.bucket_exists.return_value = True
        mock_minio_class.return_value = mock_client

        from martin.utils.oss_client import MinioClient

        client = MinioClient()
        result = client.download_file("ct/sample.nii.gz")

        # 返回的路径应在系统临时目录中
        assert "tmp" in result.lower() or "/" in result
        assert result.endswith(".nii.gz")

    @patch("martin.utils.oss_client.Minio")
    @patch("martin.utils.oss_client.config")
    def test_bucket_property(self, mock_config, mock_minio_class):
        """bucket 属性返回配置的 bucket 名称。"""
        mock_config.minio_endpoint = "localhost:9000"
        mock_config.minio_access_key = "minioadmin"
        mock_config.minio_secret_key = "minioadmin"
        mock_config.minio_bucket_name = "my-custom-bucket"
        mock_config.minio_secure = False

        mock_client = MagicMock()
        mock_minio_class.return_value = mock_client

        from martin.utils.oss_client import MinioClient

        client = MinioClient()
        assert client.bucket == "my-custom-bucket"
