"""病例上下文功能单元测试"""

import json
from unittest.mock import MagicMock, patch

from martin.agent.agent import AgentExecutor
from martin.agent.case_context import CaseContext
from martin.agent.tools import (
    analyze_image,
    generate_report,
    get_case_context,
    reset_case_context,
    set_case_context,
    update_case_context,
)


def _unwrap(tool):
    """获取 @tool 装饰器包装的原始函数。"""
    return tool.func


class TestCaseContext:
    """测试 CaseContext 基础行为。"""

    def test_case_context_creation(self):
        """验证 CaseContext 初始化字段正确，to_dict 可序列化，is_empty 返回 True。"""
        ctx = CaseContext()
        assert ctx.patient_info == {
            "age": None,
            "gender": None,
            "smoking_history": None,
            "family_history": None,
        }
        assert ctx.image_info["modality"] == "胸部CT"
        assert ctx.nodules == []
        assert ctx.knowledge_summary == ""
        assert ctx.clinical_notes == []

        data = ctx.to_dict()
        assert "created_at" in data
        assert "updated_at" in data
        assert data["patient_info"] == ctx.patient_info
        assert ctx.is_empty() is True

    def test_update_from_detection(self):
        """验证从检测结果更新 image_info 与 nodules，结节字段保留。"""
        ctx = CaseContext()
        detection_result = {
            "image": "/data/ct/test.nii.gz",
            "total_nodules": 2,
            "nodules": [
                {"index": 1, "diameter": 8.5, "score": 0.95},
                {"index": 2, "diameter": 5.0, "score": 0.75},
            ],
        }
        ctx.update_from_detection(detection_result)

        assert ctx.image_info["image_path"] == "/data/ct/test.nii.gz"
        assert ctx.image_info["image_name"] == "test.nii.gz"
        assert len(ctx.nodules) == 2
        assert ctx.detection_completed is True
        assert ctx.nodules[0]["diameter"] == 8.5
        assert ctx.nodules[1]["score"] == 0.75
        assert ctx.is_empty() is False

    def test_detection_completed_round_trip_and_legacy_restore(self):
        """检测完成状态应持久化，旧会话含结节时仍可恢复为已检测。"""
        ctx = CaseContext()
        ctx.update_from_detection({
            "image": "/data/ct/no-nodule.nii.gz",
            "total_nodules": 0,
            "nodules": [],
        })

        restored = CaseContext.from_dict(ctx.to_dict())
        assert restored.detection_completed is True
        assert restored.nodules == []

        legacy = CaseContext.from_dict({
            "image_info": {"image_path": "/data/ct/legacy.nii.gz"},
            "nodules": [{"index": 1, "diameter": 5.0, "score": 0.8}],
        })
        assert legacy.detection_completed is True

    def test_extract_patient_info(self):
        """验证从自然语言文本中正确抽取患者信息。"""
        result = CaseContext.extract_patient_info("患者60岁男性，有20年吸烟史")
        assert result["age"] == 60
        assert result["gender"] == "男"
        assert result["smoking_history"] == "吸烟 20 年"

        result = CaseContext.extract_patient_info("女性，55岁")
        assert result["age"] == 55
        assert result["gender"] == "女"

        result = CaseContext.extract_patient_info("有肺癌家族史")
        assert result["family_history"] == "有肺癌家族史"

    def test_update_patient_info_partial(self):
        """验证部分更新患者信息时其他字段保持不变。"""
        ctx = CaseContext()
        ctx.update_patient_info({
            "age": 60,
            "gender": "男",
            "smoking_history": "吸烟 20 年",
            "family_history": "有肺癌家族史",
        })
        assert ctx.patient_info["age"] == 60
        assert ctx.patient_info["gender"] == "男"

        ctx.update_patient_info({"age": 61})
        assert ctx.patient_info["age"] == 61
        assert ctx.patient_info["gender"] == "男"
        assert ctx.patient_info["smoking_history"] == "吸烟 20 年"
        assert ctx.patient_info["family_history"] == "有肺癌家族史"

    def test_case_context_to_string(self):
        """验证 to_context_string 正确生成摘要，空上下文返回空字符串。"""
        ctx = CaseContext()
        assert ctx.to_context_string() == ""

        ctx.update_patient_info({"age": 60, "gender": "男"})
        ctx.update_from_detection({
            "image": "/data/ct/test.nii.gz",
            "total_nodules": 1,
            "nodules": [{"index": 1, "diameter": 8.5, "score": 0.95}],
        })
        text = ctx.to_context_string()

        assert "【患者信息】" in text
        assert "60 岁" in text
        assert "【影像信息】" in text
        assert "【结节摘要】" in text
        assert "结节 1" in text


class TestCaseContextTools:
    """测试与病例上下文相关的工具函数。"""

    def test_update_case_context_tool(self):
        """验证 update_case_context 工具能更新当前上下文，测试后恢复原始上下文。"""
        token = set_case_context(CaseContext())
        try:
            result = _unwrap(update_case_context)(
                user_input="患者60岁男性，有20年吸烟史"
            )
            assert "已更新病例信息" in result

            ctx = get_case_context()
            assert ctx.patient_info["age"] == 60
            assert ctx.patient_info["gender"] == "男"
            assert ctx.patient_info["smoking_history"] == "吸烟 20 年"
        finally:
            reset_case_context(token)

    @patch("martin.agent.tools.NoduleDetector")
    def test_analyze_image_updates_context(self, mock_detector):
        """验证 analyze_image 工具执行后同步更新病例上下文。"""
        mock_instance = mock_detector.return_value
        mock_instance.detect.return_value = {
            "image": "/data/ct/test.nii.gz",
            "total_nodules": 1,
            "nodules": [
                {
                    "index": 1,
                    "diameter": 8.5,
                    "score": 0.95,
                    "center": {"x": 10, "y": 20, "z": 30},
                    "dimensions": {"width": 8, "height": 8.5, "depth": 7},
                },
            ],
        }

        token = set_case_context(CaseContext())
        try:
            _unwrap(analyze_image)(image_path="/data/ct/test.nii.gz")
            ctx = get_case_context()
            assert len(ctx.nodules) == 1
            assert ctx.nodules[0]["diameter"] == 8.5
            assert ctx.image_info["image_name"] == "test.nii.gz"
        finally:
            reset_case_context(token)


class TestAgentExecutorContext:
    """测试 AgentExecutor 病例上下文注入与同步。"""

    @patch("martin.agent.agent.get_chat_model")
    def test_agent_executor_injects_context(self, mock_get_chat_model):
        """验证 invoke 时将 case_context 通过 state_schema 传递给 LangGraph agent。

        新实现已移除 invoke() 中的 CONTEXT_MESSAGE_PREFIX 消息拼接，
        改为将 case_context 作为独立字段写入 state，由 dynamic_prompt middleware 在调用 LLM 前注入。
        """
        mock_get_chat_model.return_value = MagicMock()

        case_context = CaseContext()
        case_context.update_patient_info({"age": 65, "gender": "男"})
        case_context.update_from_detection({
            "image": "/data/ct/test.nii.gz",
            "total_nodules": 1,
            "nodules": [{"index": 1, "diameter": 10.0, "score": 0.96}],
        })

        executor = AgentExecutor(tools=[], verbose=False, thread_id="test-inject")
        executor.case_context = case_context
        mock_agent = MagicMock()
        executor._agent = mock_agent
        mock_agent.invoke.return_value = {"messages": []}

        executor.invoke({"input": "请评估风险"})

        args, kwargs = mock_agent.invoke.call_args
        # state 第一个位置参数包含 messages 与 case_context 两个字段
        state = args[0]
        assert state["messages"][0] == ("human", "请评估风险")
        # case_context 作为独立字段注入（取代旧的消息拼接方式）
        injected = state["case_context"]
        assert injected["patient_info"]["age"] == 65
        assert injected["patient_info"]["gender"] == "男"
        assert injected["nodules"][0]["diameter"] == 10.0
        assert injected["nodules"][0]["index"] == 1

    @patch("martin.agent.agent.get_chat_model")
    def test_agent_executor_syncs_retrieve_knowledge(self, mock_get_chat_model):
        """工具结果应同步到 CaseContext 并写回 LangGraph checkpoint。"""
        mock_get_chat_model.return_value = MagicMock()

        executor = AgentExecutor(tools=[], verbose=False, thread_id="test-sync")
        mock_agent = MagicMock()
        executor._agent = mock_agent

        from langchain_core.messages import AIMessage, ToolMessage

        ai_msg = AIMessage(
            content="",
            tool_calls=[{
                "id": "call_1",
                "name": "retrieve_knowledge",
                "args": {"detection_context": "{}"},
            }],
        )
        tool_msg = ToolMessage(content="检索到的知识摘要", tool_call_id="1")
        mock_agent.invoke.return_value = {"messages": [ai_msg, tool_msg]}

        executor.invoke({"input": "检索知识"})
        assert executor.case_context.knowledge_summary == "检索到的知识摘要"
        mock_agent.update_state.assert_called_once()
        _, update = mock_agent.update_state.call_args.args
        assert update["case_context"]["knowledge_summary"] == "检索到的知识摘要"


class TestGenerateReportContext:
    """测试报告生成与病例上下文的融合。"""

    @patch("martin.agent.tools.chain_generate_report")
    def test_generate_report_fuses_case_context(self, mock_chain):
        """验证 generate_report 工具将非空病例上下文传递给链。"""
        mock_chain.return_value = "# 测试报告"

        detection_json = json.dumps({
            "image": "test.nii.gz",
            "total_nodules": 1,
            "nodules": [{"index": 1, "score": 0.9, "diameter": 6.0}],
        })
        case_context_json = json.dumps({
            "patient_info": {
                "age": 60,
                "gender": "男",
                "smoking_history": "吸烟 20 年",
            },
        })

        _unwrap(generate_report)(
            detection_result=detection_json,
            report_type="detailed",
            case_context=case_context_json,
        )

        args, kwargs = mock_chain.call_args
        received_context = kwargs.get("case_context")
        assert received_context
        assert received_context.get("patient_info", {}).get("age") == 60
        assert received_context.get("patient_info", {}).get("gender") == "男"
