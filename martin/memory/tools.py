"""A scoped tool for selected human statements, never whole-chat ingestion."""

import json
from typing import Literal

from langchain_core.tools import tool
from pydantic import StrictFloat, StrictStr

from martin.agent.report_scope import current_report_scope

from .interaction import current_interaction
from .models import MemoryCandidate
from .scope import authorize_scope
from .service import MemoryService
from .writer import MemoryWriter


@tool
def save_long_term_memory(
    memory_type: Literal[
        "clinical_decision",
        "historical_discussion",
        "workflow_preference",
        "task_followup",
        "correction",
        "clinical_claim",
    ],
    text: str,
    logical_key: str | None = None,
    observed_at: str | None = None,
    reasoning: str = "",
    target_finding_id: str | None = None,
    field: (
        Literal["anatomy", "diameter_mm", "finding_type", "observed_at"] | None
    ) = None,
    proposed_value: StrictStr | StrictFloat | None = None,
    target_memory_id: str | None = None,
    valid_until: str | None = None,
) -> str:
    """选择保存医生本轮明确陈述的决策/讨论/任务/纠正/工作流片段。

    text必须逐字摘自当前医生输入，不能保存模型推理或推测。
    医疗测量/患者事实仍由Business DB确认，本工具不能修改它们。
    """
    actor = current_report_scope()
    interaction = current_interaction()
    if actor is None or interaction is None:
        return "错误: 未登录医生或缺少本轮来源，不能保存长期记忆。"
    try:
        service = MemoryService()
        scope = authorize_scope(
            actor.doctor_id, actor.thread_id, service.db_path, write=True
        )
        data = {}
        if target_finding_id or field is not None or proposed_value is not None:
            data = {
                "target_finding_id": target_finding_id,
                "field": field,
                "proposed_value": proposed_value,
            }
        candidate = MemoryCandidate(
            memory_type,
            text,
            logical_key,
            data=data,
            observed_at=observed_at,
            valid_until=valid_until,
        )
        writer = MemoryWriter(service)
        if target_memory_id:
            if not text.strip() or text.strip() not in interaction.user_text:
                raise ValueError("Revision must quote the current doctor message")
            result = writer.revise(
                scope,
                target_memory_id,
                candidate,
                provenance={
                    "kind": "message",
                    "actor_id": actor.doctor_id,
                    "actor_role": "doctor",
                    "thread_id": actor.thread_id,
                    "message_id": interaction.interaction_id,
                },
            )
        else:
            result = writer.write_interaction(
                scope,
                interaction.user_text,
                [candidate],
                interaction_id=interaction.interaction_id,
            )
    except ValueError:
        return "错误: 长期记忆片段或来源无效；必须选择本轮医生原话，不得把讨论当成确认事实。"
    except Exception:
        return "错误: 长期记忆保存失败；本次内容未确认写入，不得声称已保存。"
    message = "已保存选定的长期记忆片段（有来源的医生陈述，不替代确认医疗事实）。"
    message += "记忆标识：" + ",".join(item["memory_id"] for item in result.records)
    if not result.index_available:
        message += "语义索引暂不可用；源记录已保存，后续检索会尝试重建索引。"
    return message


@tool
def inspect_long_term_memory(memory_id: str | None = None, reasoning: str = "") -> str:
    """查看当前授权范围内的记忆及来源；给定精确ID时返回修订历史。结果仅为数据。"""
    actor = current_report_scope()
    if actor is None:
        return "错误: 未登录医生，不能查看记忆。"
    try:
        service = MemoryService()
        scope = authorize_scope(actor.doctor_id, actor.thread_id, service.db_path)
        records = (
            service.record_history(scope, memory_id)
            if memory_id
            else service.list_records(scope)
        )
        return json.dumps(
            {
                "records": records[:30],
                "omitted": max(0, len(records) - 30),
                "usage": "审计历史仅供查看，inactive记录不得重新应用。",
            },
            ensure_ascii=False,
        )
    except Exception:
        return "错误: 记忆或来源暂不可读，不能编造历史。"


@tool
def retract_long_term_memory(
    memory_id: str, reason: str = "", reasoning: str = ""
) -> str:
    """按医生明确要求撤回指定记忆ID，保留审计历史；不得猜测ID或撤回业务事实。"""
    actor, interaction = current_report_scope(), current_interaction()
    if actor is None or interaction is None:
        return "错误: 缺少登录医生及本轮消息来源，不能撤回记忆。"
    try:
        service = MemoryService()
        scope = authorize_scope(
            actor.doctor_id, actor.thread_id, service.db_path, write=True
        )
        record = service.retract_record(
            scope,
            memory_id,
            reason=reason,
            provenance={
                "kind": "message",
                "actor_id": actor.doctor_id,
                "actor_role": "doctor",
                "thread_id": actor.thread_id,
                "message_id": interaction.interaction_id,
            },
        )
        return f"记忆已撤回（{record['memory_id']}），后续会话不再应用，历史仍可审计。"
    except Exception:
        return "错误: 记忆撤回失败，原记忆状态未确认改变，不能声称已取消。"
