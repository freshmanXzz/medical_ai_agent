"""Agent 工具单元测试"""
import json
import pytest
from unittest.mock import patch, MagicMock


def _unwrap(tool):
    """获取 @tool 装饰器包装的原始函数。

    langchain_core 的 @tool 装饰器将函数包装为 StructuredTool 对象，
    通过 .func 属性可获取原始可调用函数。
    """
    return tool.func


class TestAnalyzeImageTool:
    """测试 analyze_image 工具。"""

    @patch("martin.agent.tools.LungNoduleDetector")
    def test_analyze_image_file_not_found(self, mock_detector):
        """测试文件不存在时返回友好错误。"""
        mock_instance = mock_detector.return_value
        mock_instance.detect.side_effect = FileNotFoundError(
            "File not found: /nonexistent/path.nii.gz"
        )

        from martin.agent.tools import analyze_image

        result = _unwrap(analyze_image)(image_path="/nonexistent/path.nii.gz")
        assert "错误: 图像文件不存在" in result

    @patch("martin.agent.tools.LungNoduleDetector")
    def test_analyze_image_with_reasoning(self, mock_detector):
        """测试 reasoning 参数兼容性。"""
        # mock 检测返回
        mock_instance = mock_detector.return_value
        mock_instance.detect.return_value = {
            "image": "test.nii.gz",
            "total_nodules": 0,
            "nodules": [],
        }

        from martin.agent.tools import analyze_image

        tool_fn = _unwrap(analyze_image)

        # 不带 reasoning
        result1 = tool_fn(image_path="test.nii.gz")
        assert "未检测到肺部结节" in result1

        # 带 reasoning
        result2 = tool_fn(
            image_path="test.nii.gz",
            reasoning="用户提供CT图像路径，需要先分析图像获取检测结果",
        )
        assert "test.nii.gz" in result2  # 结果不受 reasoning 影响

    @patch("martin.agent.tools.LungNoduleDetector")
    def test_analyze_image_with_nodules(self, mock_detector):
        """测试检测到结节时的格式化输出。"""
        mock_instance = mock_detector.return_value
        mock_instance.detect.return_value = {
            "image": "test.nii.gz",
            "total_nodules": 2,
            "nodules": [
                {
                    "index": 1,
                    "score": 0.95,
                    "diameter": 8.5,
                    "center": {"x": 10, "y": 20, "z": 30},
                    "dimensions": {"width": 8.0, "height": 8.5, "depth": 7.0},
                },
                {
                    "index": 2,
                    "score": 0.75,
                    "diameter": 5.0,
                    "center": {"x": 15, "y": 25, "z": 35},
                    "dimensions": {"width": 4.5, "height": 5.0, "depth": 4.0},
                },
            ],
        }

        from martin.agent.tools import analyze_image

        result = _unwrap(analyze_image)(image_path="test.nii.gz")
        assert "检测到结节总数: 2 个" in result
        assert "8.50 mm" in result  # 直径格式化
        assert "95.00%" in result  # 置信度百分比


class TestRetrieveKnowledgeTool:
    """测试 retrieve_knowledge 工具。"""

    @patch("martin.agent.tools.get_vector_store")
    def test_retrieve_knowledge_invalid_json(self, mock_get_store):
        """测试传入无效 JSON 时返回友好提示。

        当向量库未初始化时，应该返回"知识库未初始化"的友好提示。
        """
        mock_get_store.return_value = None

        from martin.agent.tools import retrieve_knowledge

        result = _unwrap(retrieve_knowledge)(detection_context="invalid json")
        assert "知识库未初始化" in result

    @patch("martin.agent.tools.get_vector_store")
    @patch("martin.agent.tools.search_by_detection")
    @patch("martin.agent.tools.format_results")
    def test_retrieve_knowledge_with_reasoning(
        self, mock_format, mock_search, mock_get_store
    ):
        """测试 reasoning 参数兼容性。"""
        # mock 向量库和检索
        mock_store = MagicMock()
        mock_get_store.return_value = mock_store
        mock_search.return_value = []
        mock_format.return_value = "未检索到相关医学知识。"

        from martin.agent.tools import retrieve_knowledge

        detection_json = json.dumps({
            "image": "test.nii.gz",
            "total_nodules": 1,
            "nodules": [{"index": 1, "score": 0.9, "diameter": 6.0}],
        })

        # 带 reasoning
        result = _unwrap(retrieve_knowledge)(
            detection_context=detection_json,
            reasoning="检测到单个结节，需要检索相关诊断标准",
        )
        assert isinstance(result, str)


class TestGenerateReportTool:
    """测试 generate_report 工具。"""

    @patch("martin.agent.tools.chain_generate_report")
    def test_generate_report_with_reasoning(self, mock_chain):
        """测试 reasoning 参数兼容性。"""
        mock_chain.return_value = "# 测试报告\n\n报告内容"

        from martin.agent.tools import generate_report

        detection_json = json.dumps({
            "image": "test.nii.gz",
            "total_nodules": 1,
            "nodules": [{"index": 1, "score": 0.9, "diameter": 6.0}],
        })

        tool_fn = _unwrap(generate_report)

        # 不带 reasoning
        result1 = tool_fn(detection_result=detection_json)
        assert "测试报告" in result1

        # 带 reasoning
        result2 = tool_fn(
            detection_result=detection_json,
            reasoning="检测结果已获取，需要生成详细的病例报告",
        )
        assert "测试报告" in result2  # 不受 reasoning 影响

    @patch("martin.agent.tools.chain_generate_report")
    def test_generate_report_invalid_json(self, mock_chain):
        """测试传入无效 JSON 时返回友好提示。"""
        from martin.agent.tools import generate_report

        result = _unwrap(generate_report)(detection_result="not json")
        assert "格式无效" in result or "失败" in result

    @patch("martin.agent.tools.chain_generate_report")
    def test_generate_report_calls_chain(self, mock_chain):
        """测试 generate_report 正确调用 chain。"""
        mock_chain.return_value = "# 报告"

        from martin.agent.tools import generate_report

        detection_json = json.dumps({
            "image": "test.nii.gz",
            "total_nodules": 1,
            "nodules": [{"index": 1, "score": 0.9, "diameter": 6.0}],
        })

        result = _unwrap(generate_report)(
            detection_result=detection_json,
            report_type="brief",
            language="zh",
        )

        mock_chain.assert_called_once()
        args, kwargs = mock_chain.call_args
        assert kwargs.get("report_type") == "brief"
        assert kwargs.get("language") == "zh"
        assert result == "# 报告"
