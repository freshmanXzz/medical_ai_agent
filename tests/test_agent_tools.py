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

    @patch("martin.agent.tools.NoduleDetector")
    def test_analyze_image_file_not_found(self, mock_detector):
        """测试文件不存在时返回友好错误。"""
        mock_instance = mock_detector.return_value
        mock_instance.detect.side_effect = FileNotFoundError(
            "File not found: /nonexistent/path.nii.gz"
        )

        from martin.agent.tools import analyze_image

        result = _unwrap(analyze_image)(image_path="/nonexistent/path.nii.gz")
        assert "错误: 图像文件不存在" in result

    @patch("martin.agent.tools.is_oss_path", return_value=False)
    @patch("martin.agent.tools.NoduleDetector")
    def test_analyze_image_with_reasoning(self, mock_detector, mock_oss):
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

    @patch("martin.agent.tools.is_oss_path", return_value=False)
    @patch("martin.agent.tools.NoduleDetector")
    def test_analyze_image_with_nodules(self, mock_detector, mock_oss):
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

    @patch("martin.agent.tools.get_vector_store")
    @patch("martin.agent.tools.search_by_detection")
    @patch("martin.agent.tools.format_results")
    def test_retrieve_knowledge_normalizes_chinese_detection_keys(
        self, mock_format, mock_search, mock_get_store
    ):
        """审计日志中的中文字段应被转换后再交给检索器。"""
        mock_get_store.return_value = MagicMock()
        mock_search.return_value = []
        mock_format.return_value = "检索结果"

        from martin.agent.tools import retrieve_knowledge

        detection_json = json.dumps(
            {
                "结节总数": 6,
                "结节列表": [
                    {
                        "编号": 1,
                        "最大直径_mm": 5.02,
                        "置信度": 0.985,
                        "位置": {"x": -102.07, "y": 17.21, "z": -168.28},
                    }
                ],
            },
            ensure_ascii=False,
        )

        _unwrap(retrieve_knowledge)(detection_context=detection_json)

        normalized = mock_search.call_args.args[0]
        assert normalized["total_nodules"] == 6
        assert normalized["nodules"] == [
            {
                "编号": 1,
                "最大直径_mm": 5.02,
                "置信度": 0.985,
                "位置": {"x": -102.07, "y": 17.21, "z": -168.28},
                "index": 1,
                "diameter": 5.02,
                "score": 0.985,
                "center": {"x": -102.07, "y": 17.21, "z": -168.28},
            }
        ]


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
        assert kwargs.get("case_context") == {}
        assert result == "# 报告"

    @patch("martin.agent.tools.chain_generate_report")
    def test_generate_report_passes_case_context(self, mock_chain):
        """测试 generate_report 将病例上下文正确传递给链。"""
        mock_chain.return_value = "# 报告"

        from martin.agent.tools import generate_report

        detection_json = json.dumps({
            "image": "test.nii.gz",
            "total_nodules": 1,
            "nodules": [{"index": 1, "score": 0.9, "diameter": 6.0}],
        })
        case_context_json = json.dumps({
            "patient_info": {"age": 60, "gender": "男"},
        })

        _unwrap(generate_report)(
            detection_result=detection_json,
            report_type="detailed",
            case_context=case_context_json,
        )

        args, kwargs = mock_chain.call_args
        assert kwargs.get("case_context") == {
            "patient_info": {"age": 60, "gender": "男"},
        }

    @patch("martin.agent.tools.chain_generate_report")
    def test_generate_report_invalid_case_context(self, mock_chain):
        """测试病例上下文 JSON 无效时降级为空字典。"""
        mock_chain.return_value = "# 报告"

        from martin.agent.tools import generate_report

        detection_json = json.dumps({
            "image": "test.nii.gz",
            "total_nodules": 1,
            "nodules": [{"index": 1, "score": 0.9, "diameter": 6.0}],
        })

        _unwrap(generate_report)(
            detection_result=detection_json,
            case_context="invalid json",
        )

        args, kwargs = mock_chain.call_args
        assert kwargs.get("case_context") == {}

    @patch("martin.agent.tools.chain_generate_report")
    def test_generate_report_normalizes_chinese_detection_keys(self, mock_chain):
        """中文检测字段不能被报告链误判为无结节。"""
        mock_chain.return_value = "# 报告"

        from martin.agent.tools import generate_report

        detection_json = json.dumps(
            {
                "结节总数": 1,
                "结节列表": [
                    {"编号": 1, "最大直径_mm": 5.02, "置信度": 0.985}
                ],
            },
            ensure_ascii=False,
        )

        _unwrap(generate_report)(detection_result=detection_json)

        normalized = mock_chain.call_args.args[0]
        assert normalized["total_nodules"] == 1
        assert len(normalized["nodules"]) == 1
        assert normalized["nodules"][0]["diameter"] == 5.02
        assert normalized["nodules"][0]["score"] == 0.985


class TestUpdateCaseContextTool:
    """测试 update_case_context 工具。"""

    def test_update_case_context_extracts_info(self):
        """测试从自然语言中抽取并更新患者信息。"""
        from martin.agent.case_context import CaseContext
        from martin.agent.tools import (
            update_case_context,
            get_case_context,
            set_case_context,
        )

        original = get_case_context()
        set_case_context(CaseContext())
        try:
            result = _unwrap(update_case_context)(
                user_input="患者男性，60岁，吸烟20年，有肺癌家族史"
            )
            assert "已更新病例信息" in result
            assert "年龄 60 岁" in result
            assert "性别 男" in result
            assert "吸烟史" in result
            assert "家族史" in result

            context = get_case_context()
            assert context.patient_info["age"] == 60
            assert context.patient_info["gender"] == "男"
            assert "患者男性，60岁" in context.clinical_notes[0]
        finally:
            set_case_context(original)

    def test_update_case_context_no_info(self):
        """测试未识别到患者信息时返回友好提示。"""
        from martin.agent.case_context import CaseContext
        from martin.agent.tools import (
            update_case_context,
            get_case_context,
            set_case_context,
        )

        original = get_case_context()
        set_case_context(CaseContext())
        try:
            result = _unwrap(update_case_context)(user_input="请生成报告")
            assert "未从输入中识别到新的患者信息" in result
            assert len(get_case_context().clinical_notes) == 1
        finally:
            set_case_context(original)
