"""Request-scoped, conservative budgets for every model payload.

Ark's text tokenization endpoint is verified. Its serialized-payload count plus
message/schema framing remains an estimate, distinct from actual chat usage.
When unavailable, UTF-8 bytes and framing enforce the same conservative cap.
Prompt selection is a projection: original SQL facts and checkpoints are untouched.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from contextlib import ExitStack
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import requests
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.utils.function_calling import convert_to_openai_tool

COUNT_METHOD = "utf8_bytes_upper_bound"
MESSAGE_FRAMING = 64
SCHEMA_FRAMING = 256
PAYLOAD_FRAMING = 256


def conservative_count(value: Any) -> int:
    """Count encoded bytes, retaining Unicode and complete structured values."""
    text = (
        value
        if isinstance(value, str)
        else json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
    )
    return len(text.encode("utf-8"))


def message_dict(message: BaseMessage | dict) -> dict:
    """Account for role, tool calls, IDs and structured content, not just text."""
    if isinstance(message, dict):
        return dict(message)
    role = {"human": "user", "ai": "assistant"}.get(message.type, message.type)
    value = {"role": role, "content": message.content}
    if getattr(message, "name", None):
        value["name"] = message.name
    if isinstance(message, AIMessage) and message.tool_calls:
        value["tool_calls"] = [
            {
                "id": call.get("id"),
                "type": "function",
                "function": {
                    "name": call["name"],
                    "arguments": json.dumps(call["args"], ensure_ascii=False),
                },
            }
            for call in message.tool_calls
        ]
    if getattr(message, "tool_call_id", None):
        value["tool_call_id"] = message.tool_call_id
    value.update(getattr(message, "additional_kwargs", {}) or {})
    return value


def count_payload(payload: dict) -> int:
    """Count the final serialized payload including all bound tool schemas."""
    messages = payload.get("messages", payload.get("input", []))
    tools = payload.get("tools", [])
    return (
        conservative_count(payload)
        + PAYLOAD_FRAMING
        + MESSAGE_FRAMING * (len(messages) if isinstance(messages, list) else 1)
        + SCHEMA_FRAMING * len(tools)
    )


def estimate_messages(messages: list, tools: list | None = None) -> int:
    schemas = [convert_to_openai_tool(tool) for tool in (tools or [])]
    return count_payload(
        {"messages": [message_dict(m) for m in messages], "tools": schemas}
    )


def get_policy():
    from martin.memory.budget_policy import PolicyService

    return PolicyService().current()


def task_kind(query: str) -> str:
    from martin.memory.router import RetrievalPlan

    if any(term in query.lower() for term in ("报告", "report")):
        return "report"
    if RetrievalPlan.for_query(query).temporal:
        return "followup"
    return "qa" if query.strip() else "default"


@dataclass
class BudgetScope:
    task: str
    policy: Any
    doctor_id: str | None = None
    thread_id: str | None = None
    request_id: str = field(default_factory=lambda: str(uuid4()))
    started_at: float = field(default_factory=time.monotonic)
    calls: int = 0
    estimated_input: int = 0
    reserved_output: int = 0
    stage_batches: int = 0
    stage_tokens: int = 0
    decisions: list[dict] = field(default_factory=list)
    call_records: list[dict] = field(default_factory=list)
    tokenizer_cache: dict[str, tuple[int, str, str]] = field(default_factory=dict)
    last_source_checks: tuple = field(default_factory=tuple)
    output_preferences: dict | None = None
    degraded: bool = False

    def trace(self) -> dict:
        return {
            "request_id": self.request_id,
            "policy_version": self.policy.version,
            "task": self.task,
            "count_method": (
                self.call_records[-1].get("count_method", COUNT_METHOD)
                if self.call_records
                else COUNT_METHOD
            ),
            "tokenizer_status": (
                "available"
                if self.call_records
                and all(
                    call.get("tokenizer_status") == "available"
                    for call in self.call_records
                )
                else "tokenizer_unavailable"
            ),
            "actual_tokens": None,
            "calls": list(self.call_records),
            "call_count": self.calls,
            "input_tokens": self.estimated_input,
            "estimated_input_tokens": self.estimated_input,
            "reserved_output_tokens": self.reserved_output,
            "stage_batches": self.stage_batches,
            "stage_tokens": self.stage_tokens,
            "degraded": self.degraded,
            "items": [
                dict(
                    item_id=item.get("reference"),
                    category=item.get("category"),
                    selected=item.get("selected"),
                    reason=item.get("reason"),
                    token_count=item.get("estimated_tokens", 0),
                    source_ids=item.get("source_ids", []),
                    stage=item.get("stage"),
                )
                for item in self.decisions
            ],
            "stages": [
                {
                    "stage": item.get("stage"),
                    "reason": item.get("reason"),
                    "token_count": item.get("estimated_tokens", 0),
                }
                for item in self.decisions
                if item.get("stage") == "evidence_extraction"
            ],
            "processed_ids": list(
                dict.fromkeys(
                    item.get("reference")
                    for item in self.decisions
                    if item.get("selected")
                    and item.get("reference")
                    and item.get("stage") in {"allocation", "evidence_extraction"}
                )
            ),
            "omitted_ids": list(
                dict.fromkeys(
                    item.get("reference")
                    for item in self.decisions
                    if item.get("selected") is False and item.get("reference")
                )
            ),
        }


_scope: ContextVar[BudgetScope | None] = ContextVar("martin_budget_scope", default=None)
_dispatch_checks: ContextVar[tuple] = ContextVar("martin_dispatch_checks", default=())


def current_budget_scope() -> BudgetScope | None:
    return _scope.get()


def begin_dispatch_check(callback) -> Token:
    checks = (*_dispatch_checks.get(), callback)
    scope = current_budget_scope()
    if scope is not None:
        scope.last_source_checks = checks
    return _dispatch_checks.set(checks)


def finish_dispatch_check(token: Token) -> None:
    _dispatch_checks.reset(token)


def verify_dispatch_sources() -> None:
    for callback in _dispatch_checks.get():
        try:
            callback()
        except ContextBudgetExceeded:
            raise
        except Exception as exc:
            from martin.services.access_service import (
                AccessDeniedError,
                EntityNotFoundError,
            )

            if isinstance(exc, (AccessDeniedError, EntityNotFoundError)):
                raise ContextBudgetExceeded("scope_denied") from exc
            # A failed validator must never permit a cached source to be sent,
            # or let the report chain fall back to an apparently complete report.
            raise ContextBudgetExceeded("source_validation_unavailable") from exc


def validate_context_sources(context, selected: list, task: str) -> None:
    """Validate raw sources and every selected derived projection together."""
    from martin.memory.summaries import SummaryService

    context.validate_selected(selected, task)
    references = {item.reference for item in selected}
    summaries = SummaryService(context._service)
    for reference, payload in (
        ("MINIMAL PATIENT BACKGROUND", context.minimal_background),
        ("ON DEMAND LONG TERM SUMMARY", context.detailed_summary),
    ):
        if reference in references and not summaries.validate_materialized(
            context._scope, payload
        ):
            raise ContextBudgetExceeded("summary_source_changed", omitted=[reference])


def begin_budget_scope(
    task: str, *, policy=None, doctor_id=None, thread_id=None
) -> Token:
    return _scope.set(BudgetScope(task, policy or get_policy(), doctor_id, thread_id))


def finish_budget_scope(token: Token) -> dict:
    scope = _scope.get()
    trace = scope.trace() if scope else {}
    _scope.reset(token)
    return trace


class ContextBudgetExceeded(RuntimeError):
    """Necessary evidence cannot be safely transmitted within the budget."""

    def __init__(self, reason: str, *, processed=None, omitted=None):
        self.reason = reason
        self.processed = list(processed or [])
        self.omitted = list(omitted or [])
        scope = _scope.get()
        if scope:
            scope.degraded = True
            scope.decisions.extend(
                {
                    "stage": "degradation",
                    "category": "all",
                    "reference": ref,
                    "selected": False,
                    "reason": reason,
                }
                for ref in self.omitted
            )
        explanation = {
            "model_context_unverified": "当前模型的上下文容量尚未核实",
            "summary_source_changed": "摘要来源已变化，当前摘要不能继续使用",
            "memory_source_changed": "记忆来源已变化，当前片段不能继续使用",
            "business_source_changed": "病例事实或来源状态已变化，需重新读取后分析",
            "conflict_source_changed": "冲突证据已变化，需重新读取后核实",
            "scope_denied": "当前病例访问权限已变化，原上下文不能继续使用",
            "source_validation_unavailable": "当前来源状态无法核实，原上下文不能继续使用",
            "estimation_error": "分词计数与安全估算不一致，无法保证输入完整",
            "request_time_exceeded": "本次处理已达到时间上限",
            "request_budget_exceeded": "本次处理已达到总预算上限",
            "stage_budget_exceeded": "分批处理已达到安全上限",
            "merged_evidence_exceeds_budget": "已处理证据仍无法完整纳入",
        }.get(reason, "上下文预算不足")
        super().__init__(
            explanation + "，未完成完整分析；已处理范围 "
            f"{len(self.processed)} 项，未处理范围 {len(self.omitted)} 项。"
            "必要证据无法完整纳入，不能据此作完整报告、纵向比较或最终判断。"
        )


def _record(**decision) -> None:
    scope = _scope.get()
    if scope:
        scope.decisions.append(decision)


def provider_payload_count(
    payload: dict, *, api_key=None, base_url=None
) -> tuple[int, str, str]:
    """Verified Ark tokenization plus estimated framing, with a bounded fallback.

    This is not the exact chat billing count. The endpoint tokenizes the serialized
    payload; role, tool and provider chat framing remain explicitly estimated.
    """
    from martin.memory.budget_policy import resolve_model_context

    upper = count_payload(payload)
    if (
        not api_key
        or resolve_model_context(payload.get("model", ""), base_url) is None
        or os.environ.get("MARTIN_TOKENIZER_DISABLED") == "1"
    ):
        return upper, COUNT_METHOD, "tokenizer_unavailable"
    serialized = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    scope = current_budget_scope()
    if scope is not None and digest in scope.tokenizer_cache:
        return scope.tokenizer_cache[digest]
    try:
        timeout = 3.0
        if scope is not None:
            remaining = scope.policy.max_stage_seconds - (
                time.monotonic() - scope.started_at
            )
            if remaining <= 0:
                raise ContextBudgetExceeded("request_time_exceeded")
            timeout = min(timeout, remaining)
        response = requests.post(
            "https://ark.cn-beijing.volces.com/api/v3/tokenization",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={"model": payload["model"], "text": serialized},
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json().get("data")
        count = (
            data[0].get("total_tokens")
            if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict)
            else None
        )
        if type(count) is not int or count < 0:
            raise ValueError("Invalid tokenizer count")
        framing = count_payload(payload) - conservative_count(payload)
        estimated = count + framing
        if estimated > upper:
            if scope:
                scope.degraded = True
            _record(
                stage="tokenizer",
                category="all",
                selected=False,
                reason="estimation_error",
                estimated_tokens=estimated,
            )
            raise ContextBudgetExceeded("estimation_error")
        result = (estimated, "ark_tokenization_with_framing_estimate", "available")
    except ContextBudgetExceeded:
        raise
    except Exception:
        # Never emit the response, endpoint exception, key or clinical input.
        result = (upper, COUNT_METHOD, "tokenizer_unavailable")
    if scope is not None:
        scope.tokenizer_cache[digest] = result
    return result


def record_actual_usage(usage: Any) -> None:
    """Keep only provider usage counts, never response text or hidden reasoning."""
    scope = current_budget_scope()
    if scope is None or not scope.call_records:
        return
    if not isinstance(usage, dict) and hasattr(usage, "model_dump"):
        usage = usage.model_dump()
    if not isinstance(usage, dict):
        return
    call = scope.call_records[-1]
    for source, target in (
        ("prompt_tokens", "actual_prompt_tokens"),
        ("completion_tokens", "actual_completion_tokens"),
        ("total_tokens", "actual_total_tokens"),
    ):
        value = usage.get(source)
        if type(value) is int and value >= 0:
            call[target] = value


def guard_payload(
    payload: dict,
    *,
    policy=None,
    charge: bool = True,
    verify_model: bool = False,
    base_url=None,
    api_key=None,
) -> int:
    """Final check performed before network I/O; absent tokenizer never disables it."""
    scope = _scope.get()
    policy = policy or (scope.policy if scope else get_policy())
    if scope is not None and scope.degraded:
        raise ContextBudgetExceeded("request_already_degraded")
    verify_dispatch_sources()
    if verify_model:
        from martin.memory.budget_policy import resolve_model_context

        verified = resolve_model_context(payload.get("model", ""), base_url)
        if verified is None or policy.context_window > verified:
            if scope:
                scope.degraded = True
            _record(
                stage="final_payload",
                category="all",
                selected=False,
                reason="model_context_unverified",
                estimated_tokens=0,
            )
            raise ContextBudgetExceeded("model_context_unverified")
    estimate, method, tokenizer_status = (
        provider_payload_count(
            payload,
            api_key=api_key,
            base_url=base_url,
        )
        if verify_model
        else (count_payload(payload), COUNT_METHOD, "tokenizer_unavailable")
    )
    # Source withdrawal or permission changes can occur while the provider
    # tokenizer is running. Revalidate after that I/O, before charging or sending.
    verify_dispatch_sources()
    generation = payload.get(
        "max_completion_tokens",
        payload.get("max_tokens", payload.get("max_output_tokens")),
    )
    generation = (
        generation
        if type(generation) is int and generation > 0
        else policy.reserved_output
    )
    limit = min(
        policy.input_token_limit,
        policy.context_window - generation - policy.safety_margin,
    )
    if estimate > limit:
        _record(
            stage="final_payload",
            category="all",
            selected=False,
            reason="budget_exceeded",
            estimated_tokens=estimate,
            input_limit=limit,
        )
        if scope:
            scope.degraded = True
        raise ContextBudgetExceeded("budget_exceeded")
    if scope and time.monotonic() - scope.started_at >= policy.max_stage_seconds:
        raise ContextBudgetExceeded("request_time_exceeded")
    if scope and charge:
        # All calls, including report generation and formatting repairs, compete
        # for the same request budget and time bound.
        total = (
            scope.estimated_input
            + scope.reserved_output
            + scope.stage_tokens
            + estimate
            + generation
        )
        if (
            total > policy.max_stage_tokens
            or scope.calls >= policy.max_stage_batches + 2
            or time.monotonic() - scope.started_at > policy.max_stage_seconds
        ):
            scope.degraded = True
            _record(
                stage="request",
                category="all",
                selected=False,
                reason="request_budget_exceeded",
                estimated_tokens=estimate,
            )
            raise ContextBudgetExceeded("request_budget_exceeded")
        scope.calls += 1
        scope.estimated_input += estimate
        scope.reserved_output += generation
        scope.call_records.append(
            {
                "index": scope.calls,
                "input_tokens": estimate,
                "output_reserved": generation,
                "input_limit": limit,
                "count_method": method,
                "tokenizer_status": tokenizer_status,
                "actual_tokens": None,
            }
        )
    _record(
        stage="final_payload",
        category="all",
        selected=True,
        reason=tokenizer_status,
        estimated_tokens=estimate,
        actual_tokens=None,
    )
    return estimate


def invoke_guarded(
    model, messages, *, task="report", input_value=None, revalidate_last_sources=False
):
    """Guard standalone LCEL and repair calls, including synthetic test models."""
    from martin.llm.chat_model import BudgetedChatOpenAI

    token = begin_budget_scope(task) if current_budget_scope() is None else None
    try:
        scope = current_budget_scope()
        policy = scope.policy
        payload = {
            "model": getattr(model, "model_name", "synthetic"),
            "messages": [message_dict(message) for message in messages],
            "max_tokens": min(
                getattr(model, "max_tokens", None) or policy.reserved_output,
                policy.reserved_output,
            ),
        }
        with ExitStack() as stack:
            check_token = None
            if revalidate_last_sources and scope.last_source_checks:
                from martin.memory.lifecycle import write_lock

                checks = scope.last_source_checks

                def check():
                    for callback in checks:
                        callback()

                stack.enter_context(write_lock)
                check_token = begin_dispatch_check(check)
            try:
                guard_payload(payload, charge=not isinstance(model, BudgetedChatOpenAI))
                return model.invoke(
                    input_value if input_value is not None else messages
                )
            finally:
                if check_token is not None:
                    finish_dispatch_check(check_token)
    finally:
        if token is not None:
            finish_budget_scope(token)


@dataclass(frozen=True)
class BudgetItem:
    reference: str
    category: str
    value: Any
    protected: bool = False
    source_ids: tuple[str, ...] = ()
    boundary: str = ""
    compact: Any = None

    def text(self, *, compact: bool = False) -> str:
        value = self.compact if compact and self.compact is not None else self.value
        return (
            value
            if isinstance(value, str)
            else json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        )


@dataclass
class BudgetSelection:
    text: str
    selected_ids: list[str]
    omitted_ids: list[str]
    staged: bool = False
    selected_items: list[BudgetItem] = field(default_factory=list)

    def render_without(self, *categories: str) -> str:
        return _render(
            [item for item in self.selected_items if item.category not in categories]
        )


def _render(items: list[BudgetItem], compact=False) -> str:
    return "\n".join(
        f"[{item.category}:{item.reference}]\n{item.text(compact=compact)}"
        for item in items
    )


def _compact_preserves(item: BudgetItem) -> bool:
    """Only exact, supplied structured projections can replace protected input."""
    if not isinstance(item.value, dict) or not isinstance(item.compact, dict):
        return False
    # A projection can omit duplicated routing/provenance envelopes. Every
    # clinically meaningful scalar, data field, time, status and source stays exact.
    envelope = {
        "retrieval_method",
        "injection_reason",
        "relevance_score",
        "confidence",
        "doctor_id",
        "patient_id",
        "thread_id",
        "authority",
        "created_at",
        "updated_at",
        "provenance",
        "source_message_id",
        "source_thread_id",
        "display_text",
    }
    required = {key: value for key, value in item.value.items() if key not in envelope}
    return all(
        key in item.compact and item.compact[key] == value
        for key, value in required.items()
    )


def _stage_protected(
    items: list[BudgetItem], available: int, policy
) -> list[BudgetItem]:
    """Bounded deterministic extraction with source and completeness checks.

    This reads each protected item in source/date/type batches without making
    model calls. It never turns a summary into a confirmed clinical fact.
    """
    scope = _scope.get()
    started = time.monotonic()
    batches: list[list[BudgetItem]] = []
    current: list[BudgetItem] = []
    for item in sorted(
        items, key=lambda row: (row.boundary, row.category, row.reference)
    ):
        if conservative_count(_render([item])) + PAYLOAD_FRAMING > available:
            raise ContextBudgetExceeded(
                "single_evidence_exceeds_budget", omitted=[x.reference for x in items]
            )
        if current and (
            current[-1].boundary != item.boundary
            or conservative_count(_render(current + [item])) + PAYLOAD_FRAMING
            > available
        ):
            batches.append(current)
            current = []
        current.append(item)
    if current:
        batches.append(current)
    processed, output, total = [], [], 0
    for batch in batches:
        estimated = conservative_count(_render(batch)) + PAYLOAD_FRAMING
        batch_count = scope.stage_batches if scope else len(processed)
        consumed = scope.stage_tokens if scope else total
        if (
            batch_count >= policy.max_stage_batches
            or consumed + estimated > policy.max_stage_tokens
            or time.monotonic() - started > policy.max_stage_seconds
        ):
            processed_ids = [item.reference for item in output]
            raise ContextBudgetExceeded(
                "stage_budget_exceeded",
                processed=processed_ids,
                omitted=[
                    x.reference for x in items if x.reference not in processed_ids
                ],
            )
        total += estimated
        processed.append(batch)
        if scope:
            scope.stage_batches += 1
            scope.stage_tokens += estimated
        for item in batch:
            if item.compact is not None and not _compact_preserves(item):
                raise ContextBudgetExceeded(
                    "typed_projection_changed_evidence",
                    processed=[row.reference for row in output],
                    omitted=[row.reference for row in items if row not in output],
                )
            if item.compact is not None:
                output.append(
                    BudgetItem(
                        item.reference,
                        item.category,
                        item.compact,
                        True,
                        item.source_ids,
                        item.boundary,
                    )
                )
            else:
                output.append(item)
            _record(
                stage="evidence_extraction",
                category=item.category,
                reference=item.reference,
                source_ids=list(item.source_ids),
                selected=True,
                reason="exact_typed_projection",
                estimated_tokens=conservative_count(item.text()),
            )
    if {item.reference for item in output} != {item.reference for item in items}:
        raise ContextBudgetExceeded("incomplete_source_coverage")
    return output


def select_context(
    items: list[BudgetItem],
    *,
    available: int,
    task="default",
    policy=None,
    force_stage=False,
) -> BudgetSelection:
    """Protect required evidence, then use task quotas with unused quota lending."""
    scope = _scope.get()
    policy = policy or (scope.policy if scope else get_policy())
    unique, omitted = {}, []
    for item in items:
        if item.reference in unique:
            _record(
                stage="quality",
                category=item.category,
                reference=item.reference,
                selected=False,
                reason="duplicate",
            )
            continue
        unique[item.reference] = item
    protected = [item for item in unique.values() if item.protected]
    flexible = [item for item in unique.values() if not item.protected]
    staged = False
    if force_stage or conservative_count(_render(protected)) > available:
        staged = True
        try:
            protected = _stage_protected(protected, available, policy)
        except ContextBudgetExceeded:
            if scope:
                scope.degraded = True
            raise
        if conservative_count(_render(protected)) > available:
            if scope:
                scope.degraded = True
            raise ContextBudgetExceeded(
                "merged_evidence_exceeds_budget",
                processed=[x.reference for x in protected],
            )
    selected = list(protected)
    reasons = {item.reference: "protected" for item in protected}
    # A selected summary can cover optional raw discussions. Coverage never
    # applies to protected facts or conflicts, or to a summary that did not fit.
    summary_sources = set()
    rest = []
    summaries = sorted(
        (item for item in flexible if item.category == "summary"),
        key=lambda item: 0 if "MINIMAL" in item.reference else 1,
    )
    for item in summaries:
        if conservative_count(_render(selected + [item])) <= available:
            selected.append(item)
            reasons[item.reference] = (
                "minimal_background_priority"
                if "MINIMAL" in item.reference
                else "summary_priority"
            )
            summary_sources.update(item.source_ids)
        else:
            omitted.append(item.reference)
            reasons[item.reference] = "budget_exceeded"
    for item in flexible:
        if item.category == "summary":
            continue
        source_ids = (
            {str(item.value["memory_id"])}
            if isinstance(item.value, dict) and item.value.get("memory_id")
            else set(item.source_ids)
        )
        if source_ids and source_ids.issubset(summary_sources):
            omitted.append(item.reference)
            reasons[item.reference] = "covered_by_summary"
        else:
            rest.append(item)
    remaining = max(0, available - conservative_count(_render(selected)))
    quotas = policy.category_quotas.get(task, policy.category_quotas["default"])
    used, pending = {}, []
    for item in rest:
        size = conservative_count(_render([item])) + 1
        quota = remaining * quotas.get(item.category, quotas.get("memory", 0)) // 100
        if (
            used.get(item.category, 0) + size <= quota
            and conservative_count(_render(selected + [item])) <= available
        ):
            selected.append(item)
            used[item.category] = used.get(item.category, 0) + size
            reasons[item.reference] = "category_quota"
        else:
            pending.append(item)
    for item in pending:
        if conservative_count(_render(selected + [item])) <= available:
            selected.append(item)
            reasons[item.reference] = "borrowed_unused_quota"
        else:
            omitted.append(item.reference)
            reasons[item.reference] = "budget_exceeded"
    for item in [*protected, *flexible]:
        _record(
            stage="allocation",
            category=item.category,
            reference=item.reference,
            source_ids=list(item.source_ids),
            selected=item.reference not in omitted,
            reason=reasons[item.reference],
            estimated_tokens=conservative_count(item.text()),
        )
    return BudgetSelection(
        _render(selected), [x.reference for x in selected], omitted, staged, selected
    )


def project_history(
    messages: list[BaseMessage], *, system_message=None, tools=None, policy=None
) -> list[BaseMessage]:
    """Drop whole older turns in the model projection, preserving current tool pairs."""
    scope = _scope.get()
    policy = policy or (scope.policy if scope else get_policy())
    start = next(
        (
            i
            for i in range(len(messages) - 1, -1, -1)
            if isinstance(messages[i], HumanMessage)
        ),
        0,
    )
    fixed = [system_message] if system_message else []
    current = messages[start:]
    if estimate_messages(fixed + current, tools) > policy.input_token_limit:
        raise ContextBudgetExceeded("current_turn_exceeds_budget")
    selected = list(current)
    older = messages[:start]
    boundaries = [i for i, msg in enumerate(older) if isinstance(msg, HumanMessage)]
    for idx in reversed(range(len(boundaries))):
        left = boundaries[idx]
        right = boundaries[idx + 1] if idx + 1 < len(boundaries) else len(older)
        turn = older[left:right]
        if (
            estimate_messages(fixed + turn + selected, tools)
            <= policy.input_token_limit
        ):
            selected = turn + selected
        else:
            for message in turn:
                _record(
                    stage="history",
                    category="history",
                    reference=getattr(message, "id", None),
                    selected=False,
                    reason="budget_exceeded",
                    estimated_tokens=conservative_count(message_dict(message)),
                )
    return selected
