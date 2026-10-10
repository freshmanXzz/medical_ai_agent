"""Synthetic V2.2 REST/WS, provenance and model-output quality evidence.

Uses the isolated V2.1 harness, not a running patient's database. No credentials
or hidden reasoning are retained. Automated checks require public-answer review.
"""

import dataclasses
import json
import os
import re
import sys
import time
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from dotenv import load_dotenv

load_dotenv(REPO / ".env", override=True)
os.environ["MARTIN_ACCEPTANCE_OUTPUT_DIR"] = str(REPO / "tmp/validation")
os.environ.setdefault("EMBEDDING_DEVICE", "cpu")

import memory_governance_live_acceptance as g
import store_v1_live_acceptance as h
from langchain_core.messages import HumanMessage, SystemMessage

from martin.auth.capabilities import set_budget_admin
from martin.llm.chat_model import get_chat_model
from martin.llm.context_budget import begin_budget_scope, finish_budget_scope
from martin.memory.budget_policy import BudgetPolicy
from martin.memory.router import MemoryRetrievalRouter
from martin.memory.scope import authorize_scope
from martin.memory.service import MemoryService
from martin.memory.summaries import SummaryService

h.evidence.update(
    version="V2.2 growth and context governance",
    scope="Synthetic memory, real Ark model, REST/WS/report, isolated databases and BGE",
    public_answers=[],
    p1_public_comparison=[],
)
real_end = h.EvidenceCallback.on_llm_end
real_start = h.EvidenceCallback.on_chat_model_start
real_prompts = h.actual_prompts


def messages_start(self, serialized, messages, *, run_id, **kwargs):
    """Retain every synthetic message role, excluding provider reasoning fields."""
    real_start(self, serialized, messages, run_id=run_id, **kwargs)
    entry = next(
        item for item in h.evidence["model_calls"] if item["run_id"] == str(run_id)
    )
    entry["serialized_messages"] = [
        {
            "role": message.type,
            "content": h.clean(message.content),
            "tool_calls": h.clean(getattr(message, "tool_calls", [])),
            "tool_call_id": getattr(message, "tool_call_id", None),
        }
        for batch in messages
        for message in batch
    ]
    h.flush()


def all_role_prompts(phase):
    prompts = list(real_prompts(phase))
    for call in h.evidence["model_calls"]:
        if call["phase"] == phase:
            prompts.extend(
                json.dumps(message, ensure_ascii=False)
                for message in call.get("serialized_messages", [])
            )
    return prompts


def usage_end(self, response, *, run_id, **kwargs):
    real_end(self, response, run_id=run_id, **kwargs)
    entry = next(
        item for item in h.evidence["model_calls"] if item["run_id"] == str(run_id)
    )
    entry["usage"] = [
        generation.message.usage_metadata
        for batch in response.generations
        for generation in batch
    ]
    h.flush()


def trace(client, thread):
    response = client.get("/api/memory/budget/trace", params={"thread_id": thread})
    response.raise_for_status()
    return response.json()["trace"]


def run(client):
    client.post(
        "/api/auth/login",
        json={"username": "doctor_a", "password": "SyntheticLiveDoctorA!2026"},
    ).raise_for_status()
    service = MemoryService()
    first = h.new_thread(client, "C002")
    # Threshold generates the derived head in response background work.
    for i in range(12):
        marker = "玄翎" if i == 0 else f"合成讨论{i:02}"
        g.submit(
            client,
            first,
            "historical_discussion",
            f"{marker}：医生保留第{i}次复核讨论，等待原始影像；尚未作确认诊断。",
        )
    scope = authorize_scope("D001", first)
    for _ in range(30):
        summary = SummaryService(service).detailed_for_task(
            scope,
            "历史讨论原因",
            token_budget=2400,
            token_counter=lambda s: len(s.encode("utf-8")),
        )
        if summary.get("available") and summary.get("source_memory_ids"):
            break
        time.sleep(0.1)
    h.phase = "A_summary_followup"
    public, ok = g.answer(
        client,
        first,
        "整理历史讨论原因，并比较6mm与8mm的来源观察；不能证明病灶同一性时请明确说明。只整理合成资料。",
    )
    before_trace = trace(client, first)
    g.check(
        "A Summary and complete fact boundary",
        {
            "async summary built": summary.get("available") is True
            and bool(summary.get("source_memory_ids")),
            "summary in actual payload": any(
                item.get("selected")
                and item.get("item_id") == "ON DEMAND LONG TERM SUMMARY"
                for item in before_trace["items"]
            ),
            "real answer with both observations": ok
            and g.has_mm(public, 6)
            and g.has_mm(public, 8),
            "identity remains uncertain": g.uncertain(public),
            "trace has actual usage": bool(before_trace)
            and any(
                c.get("actual_prompt_tokens") is not None for c in before_trace["calls"]
            ),
        },
        "Review historical/current dates, source reasons and unconfirmed lesion identity.",
    )

    h.phase = "B_source_withdrawal"
    withdrawn = summary["source_memory_ids"][0]
    client.post(
        g.memory_url(first, withdrawn) + "/retract", json={"reason": "合成撤回测试"}
    ).raise_for_status()
    cached_rejected = not SummaryService(service).validate_materialized(scope, summary)
    restored = h.new_thread(client, "C002")
    public, ok = g.answer(
        client,
        restored,
        "整理当前可追溯的历史讨论，已撤回来源不得作为有效背景。没有可靠来源时请直说。",
        websocket=True,
    )
    g.check(
        "B Withdrawn summary and WS",
        {
            "cached summary refused": cached_rejected,
            "withdrawn marker absent from actual prompt": all(
                "玄翎" not in p for p in h.actual_prompts(h.phase)
            ),
            "withdrawn marker absent from answer": ok and "玄翎" not in public,
            "WS trace persisted": bool(trace(client, restored)),
        },
        "No withdrawn reasons revived; remaining doctor discussions retain source authority.",
    )

    h.phase = "C_conflict_report"
    g.submit(
        client,
        restored,
        "correction",
        "合成更正提议：F002直径拟改为9mm，尚未复核。",
        target_finding_id="F002",
        field="diameter_mm",
        proposed_value=9,
    )
    public, ok = g.answer(
        client,
        restored,
        "请生成简短报告，保留当前确认8mm与拟改9mm的冲突两侧；不能声称数据库已经更正。",
    )
    g.check(
        "C Conflict protected in report",
        {
            "conflict both values": ok and g.has_mm(public, 8) and g.has_mm(public, 9),
            "uncertainty retained": g.uncertain(public),
            "trace source conflict selected": any(
                item.get("selected")
                and "MEMORY CLAIM CONFLICTS" in (item.get("item_id") or "")
                for item in trace(client, restored)["items"]
            ),
        },
        "Confirmed 8mm stays authoritative; 9mm remains a proposal.",
    )

    h.phase = "C2_direct_report_rest"
    response = client.post(
        "/api/report/generate",
        json={"session_id": restored, "report_type": "brief", "language": "zh"},
    )
    body = g.safe_record_response("direct_report_rest", response)
    report = body.get("report", "")
    h.evidence["public_answers"].append(
        {"phase": h.phase, "channel": "report_rest", "answer": report}
    )
    direct_trace = trace(client, restored)
    g.check(
        "C2 Independent report REST and trace",
        {
            "report endpoint successful": response.status_code == 200,
            "confirmed and proposed conflict retained": g.has_mm(report, 8)
            and g.has_mm(report, 9),
            "proposal stays unverified": g.uncertain(report),
            "request-local report usage persisted": direct_trace.get("task") == "report"
            and direct_trace.get("call_count", 0) > 0
            and any(
                c.get("actual_prompt_tokens") is not None
                for c in direct_trace.get("calls", [])
            ),
        },
        "Review independent REST report, confirmed 8mm, proposed 9mm and actual usage.",
    )
    h.flush()

    h.phase = "D_budget_admin"
    me = client.get("/api/auth/me").json()
    current = client.get("/api/memory/budget/policy").json()
    denied = client.put(
        "/api/memory/budget/policy",
        json={"policy": current["policy"], "expected_version": current["version"]},
    )
    set_budget_admin("D001", True, operator_label="synthetic_acceptance_operator")
    admin_me = client.get("/api/auth/me").json()
    changed = dict(current["policy"], max_stage_seconds=60)
    saved = client.put(
        "/api/memory/budget/policy",
        json={
            "policy": changed,
            "expected_version": current["version"],
            "reason": "合成配置测试",
        },
    )
    version = saved.json().get("version")
    rolled = client.post(
        "/api/memory/budget/rollback",
        json={
            "target_version": 0,
            "expected_version": version,
            "reason": "合成回退测试",
        },
    )
    set_budget_admin("D001", False, operator_label="synthetic_acceptance_operator")
    denied_after = client.put(
        "/api/memory/budget/policy",
        json={
            "policy": current["policy"],
            "expected_version": rolled.json().get("version"),
        },
    )
    g.check(
        "D Capability policy audit rollback",
        {
            "default off": not me["capabilities"]["budget_admin"]
            and denied.status_code == 403,
            "same login capability refreshed": admin_me["capabilities"]["budget_admin"]
            is True,
            "new version saved": saved.status_code == 200 and version == 1,
            "rollback creates next version": rolled.status_code == 200
            and rolled.json()["version"] == 2,
            "revocation immediate": denied_after.status_code == 403,
        },
        "Deterministic auth/config checks; no additional patient grants.",
    )

    h.phase = "E_critical_overflow"
    set_budget_admin("D001", True, operator_label="synthetic_acceptance_operator")
    current = client.get("/api/memory/budget/policy").json()
    constrained = dict(
        current["policy"],
        context_window=8192,
        reserved_output=512,
        safety_margin=256,
        summary_tokens=128,
        minimal_background_tokens=64,
    )
    client.put(
        "/api/memory/budget/policy",
        json={"policy": constrained, "expected_version": current["version"]},
    ).raise_for_status()
    count_before = len(h.evidence["model_calls"])
    response, body = h.chat(
        client,
        h.new_thread(client, "C002"),
        "必须完整处理的合成问题：" + "合" * 3000,
        "critical_overflow",
    )
    g.check(
        "E Protected question overflow",
        {
            "explicit incomplete result": response.status_code == 200
            and "未完成完整分析" in body.get("output", ""),
            "no model dispatch": len(h.evidence["model_calls"]) == count_before,
        },
        "Insufficient budget must not produce complete analysis.",
    )
    version = client.get("/api/memory/budget/policy").json()["version"]
    client.post(
        "/api/memory/budget/rollback",
        json={"target_version": 0, "expected_version": version},
    ).raise_for_status()
    set_budget_admin("D001", False, operator_label="synthetic_acceptance_operator")

    # Same actual source snapshot, question, provider and output cap; compare only
    # projection behavior. This is not a replay of the old Agent execution engine.
    from memory_v22_quality_baseline import baseline_class

    old_class, _ = baseline_class()
    comparison_context = MemoryRetrievalRouter().retrieve(
        "D001", restored, "比较历史讨论和当前观察来源"
    )
    old_fields = {f.name for f in dataclasses.fields(old_class)}
    old_context = old_class(
        **{
            f.name: getattr(comparison_context, f.name)
            for f in dataclasses.fields(comparison_context)
            if f.name in old_fields
        }
    )
    question = "只整理合成记录中的当前8mm、既往6mm以及待核实9mm提议，注明来源边界与病灶同一性限制。"
    for label, prompt in (
        ("v21_projection", old_context.to_prompt(question)),
        ("v22_projection", comparison_context.to_prompt(question)),
    ):
        h.phase = "P1_" + label
        token = begin_budget_scope("followup")
        started = time.perf_counter()
        try:
            answer = get_chat_model().invoke(
                [SystemMessage(content=prompt), HumanMessage(content=question)]
            )
            public = answer.content
        finally:
            budget_trace = finish_budget_scope(token)
        h.evidence["p1_public_comparison"].append(
            {
                "label": label,
                "latency_seconds": time.perf_counter() - started,
                "answer": public,
                "usage": answer.usage_metadata,
                "trace": budget_trace,
                "retained_values": {str(n): g.has_mm(public, n) for n in (6, 8, 9)},
                "uncertainty": g.uncertain(public),
                "model_calls": budget_trace["call_count"],
            }
        )
        h.flush()


def run_report_source_only(client):
    """Verify the last report-source fix without replaying unrelated scenarios."""
    client.post(
        "/api/auth/login",
        json={"username": "doctor_a", "password": "SyntheticLiveDoctorA!2026"},
    ).raise_for_status()
    thread = h.new_thread(client, "C002")
    g.submit(
        client,
        thread,
        "correction",
        "合成更正提议：F002拟改9mm，尚未复核。",
        target_finding_id="F002",
        field="diameter_mm",
        proposed_value=9,
    )
    h.phase = "F_empty_knowledge_report"
    response = client.post(
        "/api/report/generate",
        json={"session_id": thread, "report_type": "brief", "language": "zh"},
    )
    body = g.safe_record_response("empty_knowledge_report", response)
    report = body.get("report", "")
    budget_trace = trace(client, thread)
    h.evidence["public_answers"].append(
        {"phase": h.phase, "transport": "report_rest", "answer": report}
    )
    g.check(
        "F Empty knowledge has no fabricated reference",
        {
            "report endpoint successful": response.status_code == 200,
            "confirmed/proposed boundary retained": g.has_mm(report, 8)
            and g.has_mm(report, 9)
            and g.uncertain(report),
            "empty placeholder not allocated as knowledge source": not any(
                item.get("selected")
                and str(item.get("item_id", "")).startswith("REPORT RAG:")
                for item in budget_trace.get("items", [])
            ),
            "no fabricated knowledge citation": not re.search(
                r"(?:\[|【)\s*知识\s*\d+|\[rag:REPORT RAG:", report
            ),
            "actual report usage persisted": any(
                call.get("actual_prompt_tokens") is not None
                for call in budget_trace.get("calls", [])
            ),
        },
        "Review no retrieved knowledge, no unsupported citations, 8mm confirmed and 9mm unverified.",
    )
    h.flush()


def main():
    h.record_response = g.safe_record_response
    h.run_scenarios = (
        run_report_source_only if "--report-source-only" in sys.argv else run
    )
    with (
        patch.object(MemoryRetrievalRouter, "retrieve", g.recorded_retrieve),
        patch.object(h.EvidenceCallback, "on_llm_end", usage_end),
        patch.object(h.EvidenceCallback, "on_chat_model_start", messages_start),
        patch.object(h, "actual_prompts", all_role_prompts),
    ):
        result = h.main()
    print("Public-answer review required; synthetic scope only.", flush=True)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
