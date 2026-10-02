"""A scoped tool for selected human statements, never whole-chat ingestion."""

from typing import Literal

from langchain_core.tools import tool

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
    ],
    text: str,
    logical_key: str | None = None,
    observed_at: str | None = None,
    reasoning: str = "",
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
        candidate = MemoryCandidate(
            memory_type, text, logical_key, observed_at=observed_at
        )
        result = MemoryWriter(service).write_interaction(
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
    if not result.index_available:
        message += "语义索引暂不可用；源记录已保存，后续检索会尝试重建索引。"
    return message
