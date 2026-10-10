"""Report inputs from confirmed Findings retain their source and observation dates."""

from copy import deepcopy

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from martin.llm import chain
from martin.llm.context_budget import begin_budget_scope, finish_budget_scope
from martin.memory.budget_policy import BudgetPolicy

REPORT_TYPES = ("brief", "detailed", "research")


@pytest.mark.parametrize("report_type", REPORT_TYPES)
@pytest.mark.parametrize("with_knowledge", [False, True])
def test_report_rag_placeholder_has_no_source_identity(
    monkeypatch, report_type, with_knowledge
):
    prompts = _capture_prompt(monkeypatch)
    knowledge = (
        "【参考资料1】合成知识原文，来源 synthetic-guideline。"
        if with_knowledge
        else "暂无相关知识库资料。"
    )
    monkeypatch.setattr(chain, "_build_knowledge_context", lambda *_: knowledge)
    token = begin_budget_scope("report", policy=BudgetPolicy())
    try:
        assert chain.generate_report(_finding_result(), report_type) == "合成病例报告"
    finally:
        trace = finish_budget_scope(token)
    selected_rag = [
        item
        for item in trace["items"]
        if item["stage"] == "allocation"
        and item["category"] == "rag"
        and item["selected"]
    ]
    system, human = prompts[0]
    if with_knowledge:
        assert selected_rag
        assert "synthetic-guideline" in human.content
    else:
        assert not selected_rag
        assert "REPORT RAG:" not in human.content
        assert "不能生成知识引用编号或RAG引用" in system.content
        assert "暂无入选知识库资料" in human.content


def _finding_result():
    return {
        "image": "synthetic-current-case",
        "source": "business_findings",
        "source_case_id": "synthetic-current-case",
        "detection_completed": False,
        "total_nodules": 2,
        "nodules": [
            {
                "index": 1,
                "finding_id": "synthetic-finding-1",
                "source_case_id": "synthetic-current-case",
                "anatomy": "右肺上叶",
                "observed_at": "2026-09-01",
                "diameter": 8.0,
            },
            {
                "index": 2,
                "finding_id": "synthetic-finding-2",
                "source_case_id": "synthetic-current-case",
                "anatomy": "左肺下叶",
                "observed_at": "2026-09-02",
                "diameter": 4.0,
            },
        ],
    }


def _capture_prompt(monkeypatch):
    prompts = []

    def respond(prompt):
        prompts.append(prompt.to_messages())
        return AIMessage(content="合成病例报告")

    monkeypatch.setattr(chain, "get_chat_model", lambda: RunnableLambda(respond))
    monkeypatch.setattr(chain, "_build_knowledge_context", lambda *_args: "暂无资料")
    return prompts


@pytest.mark.parametrize("report_type", REPORT_TYPES)
def test_finding_anatomy_dates_and_diameter_reach_model(monkeypatch, report_type):
    result = _finding_result()
    before = deepcopy(result)
    prompts = _capture_prompt(monkeypatch)

    assert chain.generate_report(result, report_type) == "合成病例报告"

    assert len(prompts) == 1
    system, human = prompts[0]
    assert "【检查信息】" in human.content
    assert "结节 1 观察/检查日期：2026-09-01" in human.content
    assert "结节 2 观察/检查日期：2026-09-02" in human.content
    assert "【影像所见】" in human.content
    findings = human.content.split("【影像所见】", 1)[1]
    assert "右肺上叶" in findings
    assert "左肺下叶" in findings
    assert "8.00" in findings
    assert "4.00" in findings
    assert "置信度" in findings and "未提供" in findings
    assert "0.00%" not in human.content
    assert "不表示本轮上传CT或完成自动检测" in system.content
    assert "不得将其写为报告生成日期" in system.content
    assert "检查方式、扫描参数、重建方式、图像质量和检测置信度" in system.content
    assert result == before


@pytest.mark.parametrize("report_type", REPORT_TYPES)
def test_finding_fallback_keeps_facts_without_inventing_ct(monkeypatch, report_type):
    result = _finding_result()
    before = deepcopy(result)

    def unavailable():
        raise RuntimeError("synthetic model unavailable")

    monkeypatch.setattr(chain, "create_diagnosis_chain", unavailable)
    report = chain.generate_report(result, report_type)

    assert "报告生成失败" not in report
    assert "【检查信息】" in report
    assert "结节 1 观察/检查日期：2026-09-01" in report
    assert "结节 2 观察/检查日期：2026-09-02" in report
    assert "【影像所见】" in report
    findings = report.split("【影像所见】", 1)[1]
    assert "右肺上叶" in findings
    assert "左肺下叶" in findings
    assert "8.00" in findings and "4.00" in findings
    assert "置信度" in findings and "未提供" in findings
    assert "检查方式: 胸部CT" not in report
    assert "重建方式: 标准重建" not in report
    assert "分析方法: AI结节检测" not in report
    assert "图像质量: 良好" not in report
    assert "共检测到" not in report
    assert "生成日期: 2026-09" not in report
    if report_type == "research":
        assert "平均置信度: 未提供" in report
        assert "置信度 0/2" in report
    assert result == before


@pytest.mark.parametrize("report_type", REPORT_TYPES)
def test_missing_finding_location_and_date_are_explicit(monkeypatch, report_type):
    result = _finding_result()
    result["nodules"] = [dict(result["nodules"][0], anatomy=None, observed_at=None)]
    result["total_nodules"] = 1
    prompts = _capture_prompt(monkeypatch)

    assert chain.generate_report(result, report_type) == "合成病例报告"

    human = prompts[0][-1].content
    assert "结节 1 观察/检查日期：未提供" in human
    assert "右肺上叶" not in human
    assert "解剖部位" in human and "未提供" in human
    report = chain._generate_template_report(result, report_type)
    assert "结节 1 观察/检查日期：未提供" in report
    assert "解剖部位" in report and "未提供" in report
    assert "右肺上叶" not in report


@pytest.mark.parametrize("report_type", REPORT_TYPES)
def test_no_current_facts_are_not_a_negative_detection(monkeypatch, report_type):
    result = {
        "image": "synthetic-empty-case",
        "source": "insufficient_data",
        "source_case_id": "synthetic-empty-case",
        "detection_completed": False,
        "total_nodules": 0,
        "nodules": [],
    }
    prompts = _capture_prompt(monkeypatch)

    assert chain.generate_report(result, report_type) == "合成病例报告"

    system, human = prompts[0]
    assert "资料不足" in human.content
    assert "结节数量未知" in human.content
    assert "结节数量: 0" not in human.content
    assert "资料缺失表述为未检测到结节或未见异常" in system.content

    report = chain._generate_template_report(result, report_type)
    assert "资料不足" in report
    assert "未检测到" not in report
    assert "未见异常" not in report
    assert "结节总数: 0" not in report
    assert "图像质量: 良好" not in report
    assert "平均直径: 0.00" not in report
