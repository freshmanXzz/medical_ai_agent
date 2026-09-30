"""Business Findings need not contain detector confidence or image geometry."""

from copy import deepcopy

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from martin.llm import chain


REPORT_TYPES = ("brief", "detailed", "research")


def _result(nodules):
    return {"image": "synthetic-finding", "total_nodules": len(nodules), "nodules": nodules}


@pytest.mark.parametrize("report_type", REPORT_TYPES)
@pytest.mark.parametrize("missing_kind", ("null", "omitted"))
def test_missing_score_reaches_report_model(monkeypatch, report_type, missing_kind):
    nodule = {"index": 1, "diameter": 8.0}
    if missing_kind == "null":
        nodule.update(score=None, center=None, dimensions=None)
    detection = _result([nodule])
    before = deepcopy(detection)
    prompts = []

    def respond(prompt):
        prompts.append(prompt.to_messages())
        return AIMessage(content="合成报告已生成")

    monkeypatch.setattr(chain, "get_chat_model", lambda: RunnableLambda(respond))
    monkeypatch.setattr(chain, "_build_knowledge_context", lambda *_args: "暂无相关知识库资料。")

    assert chain.generate_report(detection, report_type) == "合成报告已生成"
    assert len(prompts) == 1
    prompt = prompts[0][-1].content
    assert "8.00" in prompt
    assert "未提供" in prompt
    assert "0.00%" not in prompt
    assert detection == before


@pytest.mark.parametrize("report_type", REPORT_TYPES)
@pytest.mark.parametrize("missing_kind", ("null", "omitted"))
def test_template_handles_missing_measurements(monkeypatch, report_type, missing_kind):
    nodule = {"index": 1}
    if missing_kind == "null":
        nodule.update(diameter=None, score=None, center=None, dimensions=None)
    detection = _result([nodule])
    before = deepcopy(detection)

    def unavailable():
        raise RuntimeError("synthetic model failure")

    monkeypatch.setattr(chain, "create_diagnosis_chain", unavailable)
    report = chain.generate_report(detection, report_type)

    assert "报告生成失败" not in report
    assert "未提供" in report
    assert "0.00" not in report
    assert detection == before
    if report_type == "detailed":
        assert "不能根据缺失的检测置信度判断风险" in report
        assert "当前模板不作风险分级" in report
        assert "个低风险结节" not in report
    if report_type == "research":
        assert "平均置信度: 未提供" in report
        assert "置信度 0/1" in report


def test_partial_research_statistics_use_only_provided_values():
    detection = _result([
        {"index": 1, "diameter": 8.0, "score": None},
        {"index": 2, "diameter": None, "score": 0.9},
    ])

    report = chain._generate_template_report(detection, "research")

    assert "平均直径: 8.00 mm" in report
    assert "平均置信度: 0.9000" in report
    assert "直径 1/2，置信度 1/2" in report
    assert "资料不完整，不能依据缺失的置信度判断" in report
    assert '"score": null' in report


def test_existing_complete_measurements_keep_numeric_formats():
    nodule = {
        "index": 1,
        "diameter": 8.0,
        "score": 0.9,
        "center": {"x": 1, "y": 2, "z": 3},
        "dimensions": {"width": 4, "height": 5, "depth": 6},
    }
    detection = _result([nodule])

    assert chain._build_nodules_detail(detection, "brief") == (
        "- 结节 1: 直径 8.00mm, 置信度 90.00%"
    )
    assert chain._build_nodules_detail(detection, "detailed") == (
        "\n结节 1:"
        "\n  - 位置: (1.00, 2.00, 3.00) mm"
        "\n  - 尺寸: 4.00 x 5.00 x 6.00 mm"
        "\n  - 最大直径: 8.00 mm"
        "\n  - 检测置信度: 0.9000 (90.00%)"
    )
    assert chain._build_nodules_detail(detection, "research") == (
        "索引 | 直径(mm) | 置信度 | X | Y | Z\n"
        "-----|----------|--------|-----|-----|-----\n"
        "1 | 8.00 | 0.9000 | 1.00 | 2.00 | 3.00"
    )
    assert "高风险结节（直径≥8mm或置信度>95%）" in (
        chain._generate_template_report(detection, "detailed")
    )
    assert "平均置信度: 0.9000" in chain._generate_template_report(detection, "research")


@pytest.mark.parametrize("report_type", REPORT_TYPES)
def test_empty_detection_keeps_existing_no_nodule_report(report_type):
    detection = _result([])

    assert chain._build_nodules_detail(detection, report_type) == "无"
    assert "未检测到" in chain._generate_template_report(detection, report_type)


def test_explicit_zero_measurements_remain_distinct_from_missing():
    detail = chain._build_nodules_detail(
        _result([{"index": 1, "diameter": 0.0, "score": 0.0}]), "brief"
    )

    assert "直径 0.00mm" in detail
    assert "置信度 0.00%" in detail
    assert "未提供" not in detail
