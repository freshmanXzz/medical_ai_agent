"""V2.2 T11-T16 hard constraints, using synthetic evidence and no model network."""

import logging
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver
from pydantic import PrivateAttr

from martin.llm.context_budget import (
    BudgetItem,
    ContextBudgetExceeded,
    begin_budget_scope,
    begin_dispatch_check,
    conservative_count,
    count_payload,
    current_budget_scope,
    estimate_messages,
    finish_budget_scope,
    finish_dispatch_check,
    guard_payload,
    invoke_guarded,
    project_history,
    provider_payload_count,
    select_context,
    validate_context_sources,
)
from martin.memory.budget_policy import BudgetPolicy


def _policy(**kwargs):
    return replace(BudgetPolicy(), **kwargs)


@tool
def synthetic_schema_tool(query: str, required_evidence: str) -> str:
    """Synthetic tool with schema documentation included in the model budget."""
    return "synthetic result"


def test_t11_count_includes_system_roles_tool_calls_schema_and_output_reserve():
    messages = [SystemMessage(content="固定安全要求"), HumanMessage(content="当前问题")]
    plain = estimate_messages(messages)
    with_schema = estimate_messages(messages, [synthetic_schema_tool])
    with_tools = estimate_messages(
        messages
        + [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "synthetic_schema_tool",
                        "id": "call-1",
                        "args": {"query": "查询", "required_evidence": "证据"},
                    }
                ],
            ),
            ToolMessage(content="来源A的检索证据", tool_call_id="call-1"),
        ],
        [synthetic_schema_tool],
    )
    assert with_tools > with_schema > plain
    payload = {
        "messages": [{"role": "user", "content": "x" * 2000}],
        "max_tokens": 8192,
    }
    with pytest.raises(ContextBudgetExceeded):
        guard_payload(payload, policy=_policy(context_window=10000, safety_margin=512))
    assert conservative_count("汉字") == 6


def test_t11_verified_model_required_unknown_profile_never_transmits(monkeypatch):
    post = Mock()
    monkeypatch.setattr("martin.llm.context_budget.requests.post", post)
    with pytest.raises(ContextBudgetExceeded) as exc:
        guard_payload(
            {"model": "unknown-provider", "messages": []},
            verify_model=True,
            base_url="https://ark.cn-beijing.volces.com/api/plan/v3",
            api_key="synthetic-key",
        )
    assert exc.value.reason == "model_context_unverified"
    post.assert_not_called()


@pytest.mark.parametrize("failure", ["timeout", "invalid_count", "negative_count"])
def test_t11_tokenizer_failure_preserves_conservative_hard_limit(monkeypatch, failure):
    response = Mock()
    if failure == "timeout":
        post = Mock(side_effect=TimeoutError("synthetic unavailable"))
    else:
        response.json.return_value = {
            "data": [{"total_tokens": "12" if failure == "invalid_count" else -1}]
        }
        post = Mock(return_value=response)
    monkeypatch.setattr("martin.llm.context_budget.requests.post", post)
    payload = {
        "model": "deepseek-v4.1-flash",
        "messages": [{"role": "user", "content": "x" * 8000}],
    }
    count, method, status = provider_payload_count(
        payload,
        api_key="synthetic-key",
        base_url="https://ark.cn-beijing.volces.com/api/plan/v3",
    )
    assert count == count_payload(payload)
    assert method == "utf8_bytes_upper_bound" and status == "tokenizer_unavailable"
    with pytest.raises(ContextBudgetExceeded):
        guard_payload(
            payload,
            policy=_policy(context_window=8192, reserved_output=512, safety_margin=256),
            verify_model=True,
            base_url="https://ark.cn-beijing.volces.com/api/plan/v3",
            api_key="synthetic-key",
        )


def test_t11_provider_estimate_and_hash_cache_never_claim_exact_chat_usage(monkeypatch):
    response = Mock()
    response.json.return_value = {"data": [{"total_tokens": 20}]}
    post = Mock(return_value=response)
    monkeypatch.setattr("martin.llm.context_budget.requests.post", post)
    token = begin_budget_scope("qa", policy=_policy())
    try:
        payload = {
            "model": "deepseek-v4.1-flash",
            "messages": [{"role": "user", "content": "合成输入"}],
        }
        first = provider_payload_count(
            payload,
            api_key="synthetic-key",
            base_url="https://ark.cn-beijing.volces.com/api/plan/v3",
        )
        assert (
            provider_payload_count(
                payload,
                api_key="synthetic-key",
                base_url="https://ark.cn-beijing.volces.com/api/plan/v3",
            )
            == first
        )
        assert first[1] == "ark_tokenization_with_framing_estimate"
        assert post.call_count == 1
        assert "text" in post.call_args.kwargs["json"]
        assert all(len(key) == 64 for key in current_budget_scope().tokenizer_cache)
    finally:
        finish_budget_scope(token)


def test_t11_provider_count_above_upper_bound_is_rejected(monkeypatch):
    response = Mock()
    response.json.return_value = {"data": [{"total_tokens": 100000}]}
    monkeypatch.setattr(
        "martin.llm.context_budget.requests.post", Mock(return_value=response)
    )
    token = begin_budget_scope("qa", policy=_policy())
    try:
        with pytest.raises(ContextBudgetExceeded) as exc:
            provider_payload_count(
                {"model": "deepseek-v4.1-flash", "messages": []},
                api_key="synthetic-key",
                base_url="https://ark.cn-beijing.volces.com/api/plan/v3",
            )
        assert exc.value.reason == "estimation_error"
        assert current_budget_scope().trace()["degraded"]
    finally:
        finish_budget_scope(token)


def test_t12_soft_quota_can_borrow_unused_categories_and_record_omission():
    token = begin_budget_scope("qa", policy=_policy())
    try:
        items = [
            BudgetItem("rag-a", "rag", "a" * 500),
            BudgetItem("rag-b", "rag", "b" * 900),
        ]
        selected = select_context(items, available=800, task="qa")
        assert selected.selected_ids == ["rag-a"]
        assert selected.omitted_ids == ["rag-b"]
        trace = current_budget_scope().trace()
        assert any(item["reason"] == "borrowed_unused_quota" for item in trace["items"])
        assert any(
            item["item_id"] == "rag-b" and item["reason"] == "budget_exceeded"
            for item in trace["items"]
        )
        assert "a" * 50 not in str(trace)
    finally:
        finish_budget_scope(token)


def test_t13_task_signal_changes_soft_quota_selection_under_same_hard_limit():
    quotas = {
        kind: {
            "rag": 90 if kind == "qa" else 0,
            "memory": 0 if kind == "qa" else 90,
            "summary": 0,
            "history": 10,
        }
        for kind in ("qa", "report", "followup", "default")
    }
    policy = _policy(category_quotas=quotas)
    items = [
        BudgetItem("memory", "memory", "m" * 400),
        BudgetItem("rag", "rag", "r" * 400),
    ]
    qa = select_context(items, available=600, task="qa", policy=policy)
    report = select_context(items, available=600, task="report", policy=policy)
    assert qa.selected_ids == ["rag"]
    assert report.selected_ids == ["memory"]
    assert conservative_count(qa.text) <= 600 and conservative_count(report.text) <= 600


def test_t12_selected_summary_covers_only_optional_raw_sources():
    raw = BudgetItem(
        "raw-M1",
        "memory",
        {"memory_id": "M1", "content": "raw discussion"},
        source_ids=("M1",),
    )
    required = BudgetItem(
        "conflict",
        "memory",
        {"memory_id": "M1", "business_value": 4, "proposed_value": 8},
        True,
        ("M1",),
    )
    summary = BudgetItem(
        "ON DEMAND LONG TERM SUMMARY",
        "summary",
        "source-labelled summary",
        source_ids=("M1",),
    )
    token = begin_budget_scope("followup", policy=_policy())
    try:
        selected = select_context([raw, required, summary], available=1000)
        assert (
            "conflict" in selected.selected_ids
            and summary.reference in selected.selected_ids
        )
        assert selected.omitted_ids == ["raw-M1"]
        allocations = [
            item
            for item in current_budget_scope().trace()["items"]
            if item["stage"] == "allocation"
        ]
        assert len(allocations) == 3
        assert (
            next(item for item in allocations if item["item_id"] == "raw-M1")["reason"]
            == "covered_by_summary"
        )
    finally:
        finish_budget_scope(token)


def test_t12_unselected_summary_cannot_suppress_available_raw_evidence():
    raw = BudgetItem(
        "raw-M1",
        "memory",
        {"memory_id": "M1", "content": "available raw discussion"},
        source_ids=("M1",),
    )
    summary = BudgetItem(
        "ON DEMAND LONG TERM SUMMARY", "summary", "s" * 2000, source_ids=("M1",)
    )
    selected = select_context([raw, summary], available=500, policy=_policy())
    assert selected.selected_ids == ["raw-M1"]
    assert summary.reference in selected.omitted_ids


def _protected_items(count=4):
    items = []
    for number in range(count):
        exact = {
            "finding_id": f"F{number}",
            "diameter_mm": number + 1.25,
            "observed_at": ("2024-01-01", "2025-01-01", "2026-01-01", "2026-06-01")[
                number % 4
            ],
            "status": "confirmed",
            "source_case_id": f"C{number}",
            "source_type": "business_finding",
            "lesion_identity": "lesion_identity_unconfirmed",
        }
        items.append(
            BudgetItem(
                f"F{number}",
                "memory",
                dict(exact, provenance={"redundant": "x" * 900}),
                True,
                (f"F{number}",),
                exact["observed_at"],
                exact,
            )
        )
    return items


def test_t14_stages_preserve_all_typed_values_dates_ids_and_conflict_sides():
    token = begin_budget_scope("followup", policy=_policy())
    try:
        items = _protected_items()
        conflict = {
            "source_finding_id": "F0",
            "source_memory_id": "M1",
            "field": "diameter_mm",
            "business_value": 1.25,
            "proposed_value": 9.0,
            "status": "conflict",
        }
        items.append(
            BudgetItem(
                "conflict",
                "memory",
                conflict,
                True,
                ("F0", "M1"),
                "2026-01-01",
                conflict,
            )
        )
        selected = select_context(items, available=2100, task="followup")
        assert selected.staged
        assert set(selected.selected_ids) == {"F0", "F1", "F2", "F3", "conflict"}
        assert not selected.omitted_ids
        for key in (
            "business_value",
            "proposed_value",
            "source_finding_id",
            "source_memory_id",
            "observed_at",
        ):
            assert key in selected.text
        for value in ("1.25", "2.25", "3.25", "4.25", "9.0"):
            assert value in selected.text
        for original in items[:4]:
            result = next(
                item
                for item in selected.selected_items
                if item.reference == original.reference
            )
            assert result.value == original.compact
            assert original.compact["observed_at"] in selected.text
            assert original.compact["source_case_id"] in selected.text
            assert result.value["lesion_identity"] == "lesion_identity_unconfirmed"
        trace = current_budget_scope().trace()
        assert trace["stage_batches"] == 4
        stages = [
            item for item in trace["items"] if item["stage"] == "evidence_extraction"
        ]
        assert {item["item_id"] for item in stages} == set(selected.selected_ids)
        assert all(item["selected"] and item["source_ids"] for item in stages)
    finally:
        finish_budget_scope(token)


def test_t14_bounded_stage_failure_is_explicit_and_original_evidence_survives():
    items = _protected_items()
    before = deepcopy(items)
    token = begin_budget_scope("followup", policy=_policy(max_stage_batches=1))
    try:
        with pytest.raises(ContextBudgetExceeded) as exc:
            select_context(items, available=1700, task="followup")
        assert exc.value.processed == ["F0"]
        assert exc.value.omitted == ["F1", "F2", "F3"]
        assert "未处理范围" in str(exc.value)
        assert items == before
        assert current_budget_scope().degraded
    finally:
        finish_budget_scope(token)


def test_t14_projection_cannot_alter_a_protected_measurement():
    items = _protected_items()
    items[0] = replace(items[0], compact=dict(items[0].compact, diameter_mm=999))
    with pytest.raises(ContextBudgetExceeded):
        select_context(items, available=1700, policy=_policy())


def test_t15_history_projection_preserves_current_question_tool_pair_and_checkpoint():
    messages = [
        HumanMessage(content="old-" + "x" * 6500, id="old-user"),
        AIMessage(content="旧答复", id="old-ai"),
        HumanMessage(content="当前核心问题", id="current-user"),
        AIMessage(
            content="",
            tool_calls=[{"id": "tool-1", "name": "synthetic_schema_tool", "args": {}}],
        ),
        ToolMessage(content="当前确认数值和来源", tool_call_id="tool-1"),
    ]
    before = deepcopy(messages)
    selected = project_history(
        messages,
        system_message=SystemMessage(content="不可删除的安全约束"),
        tools=[synthetic_schema_tool],
        policy=_policy(context_window=8192, reserved_output=1024, safety_margin=512),
    )
    assert selected == messages[2:]
    assert messages == before
    assert isinstance(selected[0], HumanMessage)
    assert selected[-1].tool_call_id == selected[-2].tool_calls[0]["id"]


class HistoryCaptureModel(BaseChatModel):
    _inputs: list = PrivateAttr(default_factory=list)

    @property
    def _llm_type(self):
        return "synthetic-history-budget-contract"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self._inputs.append(deepcopy(messages))
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content="合成答复"))]
        )


def test_t15_real_graph_trims_model_history_and_keeps_restorable_checkpoint(
    monkeypatch,
):
    from martin.agent import agent as module
    from martin.agent.sessions import SessionManager

    model, saver = HistoryCaptureModel(), MemorySaver()
    policy = _policy(context_window=32768, reserved_output=512, safety_margin=256)
    monkeypatch.setattr(module, "get_chat_model", lambda: model)
    monkeypatch.setattr(
        module, "_get_thinking_logger", lambda: logging.getLogger("synthetic-v22")
    )
    monkeypatch.setattr("martin.llm.context_budget.get_policy", lambda: policy)
    monkeypatch.setattr(module, "get_policy", lambda: policy)
    executor = module.AgentExecutor(
        tools=[], verbose=False, thread_id="synthetic-history", checkpointer=saver
    )
    first, second, current = (
        "first-" + "a" * 13000,
        "second-" + "b" * 13000,
        "当前核心问题",
    )
    assert executor.invoke({"input": first})["output"] == "合成答复"
    assert executor.invoke({"input": second})["output"] == "合成答复"
    result = executor.invoke({"input": current})
    assert result["output"] == "合成答复"
    final_humans = [
        message.content
        for message in model._inputs[-1]
        if isinstance(message, HumanMessage)
    ]
    assert current in final_humans and first not in final_humans
    restored = SessionManager(saver).get_messages("synthetic-history")
    assert [message.content for message in restored if message.role == "User"] == [
        first,
        second,
        current,
    ]
    assert any(
        item["category"] == "history" and not item["selected"]
        for item in result["budget_trace"]["items"]
    )


def test_t16_transport_guard_sees_bound_tool_schema_before_network(monkeypatch):
    from martin.llm.chat_model import BudgetedChatOpenAI

    monkeypatch.setenv("MARTIN_TOKENIZER_DISABLED", "1")
    model = BudgetedChatOpenAI(
        model="deepseek-v4.1-flash",
        api_key="synthetic-key",
        base_url="https://ark.cn-beijing.volces.com/api/plan/v3",
        max_tokens=512,
    )
    token = begin_budget_scope(
        "qa",
        policy=_policy(context_window=8192, reserved_output=512, safety_margin=256),
    )
    try:
        payload = model._get_request_payload(
            [HumanMessage(content="当前问题")],
            tools=[
                {
                    "type": "function",
                    "function": {"name": "large-schema", "description": "x" * 8000},
                }
            ],
        )
        pytest.fail(f"oversized schema passed: {len(payload)}")
    except ContextBudgetExceeded:
        assert current_budget_scope().calls == 0
    finally:
        finish_budget_scope(token)


def test_t16_report_and_repair_share_one_request_call_budget(monkeypatch):
    from martin.llm.context_budget import invoke_guarded

    model = Mock()
    model.model_name = "synthetic"
    model.max_tokens = 512
    model.invoke.return_value = AIMessage(content="合成输出")
    token = begin_budget_scope("report", policy=_policy(max_stage_batches=1))
    try:
        for _ in range(3):
            invoke_guarded(
                model,
                [
                    SystemMessage(content="格式或报告安全约束"),
                    HumanMessage(content="必要证据"),
                ],
            )
        with pytest.raises(ContextBudgetExceeded) as exc:
            invoke_guarded(model, [HumanMessage(content="超出请求调用次数")])
        assert exc.value.reason == "request_budget_exceeded"
        assert model.invoke.call_count == 3
        trace = current_budget_scope().trace()
        assert trace["call_count"] == 3 and len(trace["calls"]) == 3
    finally:
        finish_budget_scope(token)


def test_t16_legacy_http_client_guard_precedes_http(monkeypatch):
    from martin.llm.deepseek_client import DeepSeekClient

    post = Mock()
    monkeypatch.setattr("martin.llm.deepseek_client.requests.post", post)
    client = DeepSeekClient(
        api_key="synthetic-key", base_url="https://unknown.invalid", model="unknown"
    )
    with pytest.raises(ContextBudgetExceeded):
        client.chat([{"role": "user", "content": "合成输入"}])
    post.assert_not_called()


def test_t16_report_necessary_evidence_overflow_never_looks_like_complete_report(
    monkeypatch,
):
    from langchain_core.runnables import RunnableLambda

    from martin.llm import chain

    calls = []
    model = RunnableLambda(
        lambda prompt: calls.append(prompt) or AIMessage(content="不应生成完整报告")
    )
    monkeypatch.setattr(chain, "get_chat_model", lambda: model)
    monkeypatch.setattr(chain, "_build_knowledge_context", lambda *_: "暂无资料")
    evidence = {
        "image": "synthetic",
        "source": "business_findings",
        "source_case_id": "C1",
        "total_nodules": 100,
        "nodules": [
            dict(
                index=index,
                finding_id=f"F{index}",
                source_case_id="C1",
                anatomy="synthetic-location-" + "a" * 120,
                observed_at="2026-01-01",
                diameter=1 + index,
            )
            for index in range(100)
        ],
    }
    before = deepcopy(evidence)
    token = begin_budget_scope(
        "report",
        policy=_policy(
            context_window=8192,
            reserved_output=512,
            safety_margin=256,
            max_stage_batches=1,
        ),
    )
    try:
        report = chain.generate_report(evidence)
        assert "未完成完整分析" in report and "不能据此作完整报告" in report
        assert not calls
        assert evidence == before
        assert current_budget_scope().trace()["degraded"]
        assert current_budget_scope().stage_batches == 1
    finally:
        finish_budget_scope(token)


@pytest.fixture
def dispatch_runtime(entity_db):
    from martin.memory.models import MemoryCandidate
    from martin.memory.router import MemoryRetrievalRouter
    from martin.memory.scope import authorize_scope
    from martin.memory.service import MemoryService
    from martin.memory.writer import MemoryWriter
    from martin.services.thread_service import ThreadService

    service = MemoryService(entity_db)
    thread = ThreadService(entity_db).create_thread("D001", "C002")
    scope = authorize_scope("D001", thread, entity_db)
    writer = MemoryWriter(service, SimpleNamespace(sync=lambda *args, **kwargs: None))
    provenance = {
        "kind": "message",
        "actor_id": scope.doctor_id,
        "actor_role": "doctor",
        "thread_id": thread,
        "message_id": "synthetic-dispatch-source",
    }
    record = writer.write(
        scope,
        [MemoryCandidate("clinical_claim", "医生口述过敏史尚待核实")],
        source_type="thread",
        source_id=thread,
        provenance=provenance,
    ).records[0]
    context = MemoryRetrievalRouter(service).retrieve(
        "D001", thread, "当前病例", modes=[]
    )
    assert any(
        item.value.get("memory_id") == record["memory_id"]
        for item in context.budget_items("当前病例")
        if isinstance(item.value, dict)
    )
    return service, scope, record, context


@pytest.mark.parametrize(
    "change",
    [
        "withdraw",
        "permission",
        "finding",
        "summary",
        "preference_withdraw",
        "preference_update",
    ],
)
def test_t16_source_changes_during_provider_tokenization_prevent_model_send(
    dispatch_runtime,
    entity_db,
    monkeypatch,
    change,
):
    from martin.db import transaction
    from martin.llm.chat_model import BudgetedChatOpenAI
    from martin.memory.router import MemoryRetrievalRouter
    from martin.memory.summaries import SummaryService
    from martin.repositories.access import AccessRepository

    service, authorized, record, context = dispatch_runtime
    selected = context.budget_items("当前病例")
    preference_provenance = {
        "kind": "api_submission",
        "actor_id": "D001",
        "actor_role": "doctor",
        "submission_id": "synthetic-preference-source",
    }
    if change.startswith("preference_"):
        record = service.save_doctor_preference(
            "D001",
            "report_style",
            {"conclusion_first": True},
            provenance=preference_provenance,
        )
        context = MemoryRetrievalRouter(service).retrieve(
            "D001", authorized.thread_id, "当前病例", modes=[]
        )
        # Aggregate preference alone must be validated even if the optional
        # underlying exact record was omitted by allocation.
        selected = [
            item
            for item in context.budget_items("当前病例")
            if item.reference.startswith("DOCTOR PREFERENCES:")
        ]
        assert len(selected) == 1
    if change == "summary":
        # Use the confirmed minimal background to exercise derived source
        # fingerprints independently of the raw business-fact projection.
        with transaction(entity_db) as connection:
            connection.execute("UPDATE patients SET sex='male' WHERE id='P001'")
        background = SummaryService(service).minimal_background(
            authorized,
            token_budget=4000,
            token_counter=conservative_count,
        )
        context = replace(context, minimal_background=background)
        object.__setattr__(context, "_scope", authorized)
        object.__setattr__(context, "_service", service)
        selected = [
            item
            for item in context.budget_items("当前病例")
            if item.category == "summary"
        ]
        assert selected
    response = Mock()
    response.json.return_value = {"data": [{"total_tokens": 20}]}

    def tokenize(*args, **kwargs):
        if change in {"withdraw", "preference_withdraw"}:
            service.retract_record(authorized, record["memory_id"])
        elif change == "preference_update":
            service.save_doctor_preference(
                "D001",
                "report_style",
                {"conclusion_first": False},
                provenance=dict(preference_provenance, submission_id="updated-source"),
            )
        else:
            with transaction(entity_db) as connection:
                if change == "permission":
                    AccessRepository(connection).revoke("D001", "P001")
                elif change == "finding":
                    connection.execute(
                        "UPDATE findings SET diameter_mm=99 WHERE case_id='C002'"
                    )
                else:
                    connection.execute(
                        "UPDATE patients SET sex='female' WHERE id='P001'"
                    )
        return response

    monkeypatch.delenv("MARTIN_TOKENIZER_DISABLED", raising=False)
    monkeypatch.setattr("martin.llm.context_budget.requests.post", tokenize)
    model = BudgetedChatOpenAI(
        model="deepseek-v4.1-flash",
        api_key="synthetic-key",
        base_url="https://ark.cn-beijing.volces.com/api/plan/v3",
        max_tokens=512,
    )
    send = Mock()
    monkeypatch.setattr(model.client, "create", send)
    token = begin_budget_scope("qa", policy=_policy())
    check_token = begin_dispatch_check(
        lambda: validate_context_sources(context, selected, "当前病例")
    )
    try:
        with pytest.raises(ContextBudgetExceeded) as exc:
            model.invoke([HumanMessage(content="合成病例问题")])
        assert (
            exc.value.reason
            == {
                "withdraw": "memory_source_changed",
                "permission": "scope_denied",
                "finding": "business_source_changed",
                "summary": "summary_source_changed",
                "preference_withdraw": "memory_source_changed",
                "preference_update": "memory_source_changed",
            }[change]
        )
        assert current_budget_scope().degraded
        assert current_budget_scope().calls == 0
        send.assert_not_called()
    finally:
        finish_dispatch_check(check_token)
        finish_budget_scope(token)


def test_t12_preference_instructions_leave_prompt_with_omitted_source(dispatch_runtime):
    from martin.memory.router import MemoryRetrievalRouter

    service, authorized, _record, _context = dispatch_runtime
    service.save_doctor_preference(
        "D001",
        "report_style",
        {"conclusion_first": True},
        provenance={
            "kind": "api_submission",
            "actor_id": "D001",
            "actor_role": "doctor",
            "submission_id": "pref",
        },
    )
    context = MemoryRetrievalRouter(service).retrieve(
        "D001", authorized.thread_id, "当前病例", modes=[]
    )
    assert "DOCTOR OUTPUT PREFERENCES" not in context.instruction_prompt("当前病例")
    preference = next(
        item
        for item in context.budget_items("当前病例")
        if item.reference.startswith("DOCTOR PREFERENCES:")
    )
    assert "DOCTOR OUTPUT PREFERENCES" in preference.value["output_constraints"]
    omitted = select_context([preference], available=0, task="qa", policy=_policy())
    assert omitted.selected_ids == [] and omitted.omitted_ids == [preference.reference]
    assert (
        "DOCTOR OUTPUT PREFERENCES"
        not in context.instruction_prompt("当前病例") + omitted.text
    )


def test_t16_agent_repair_uses_dispatched_preferences_after_cached_preference_withdrawal(
    dispatch_runtime,
    monkeypatch,
):
    from martin.agent import agent as module

    service, authorized, _record, context = dispatch_runtime
    model = HistoryCaptureModel()
    monkeypatch.setattr(module, "get_chat_model", lambda: model)
    monkeypatch.setattr(
        module, "_get_thinking_logger", lambda: logging.getLogger("synthetic-v22")
    )
    monkeypatch.setattr("martin.llm.context_budget.get_policy", lambda: _policy())
    executor = module.AgentExecutor(
        tools=[],
        verbose=False,
        thread_id=authorized.thread_id,
        doctor_id="D001",
        checkpointer=MemorySaver(),
    )
    executor.memory_context = context
    executor.report_preferences = {"conclusion_first": True}
    result = executor.invoke({"input": "生成报告"})
    assert result["output"] == "合成答复"
    assert len(model._inputs) == 1
    assert "DOCTOR OUTPUT PREFERENCES" not in str(model._inputs)


def test_t16_legacy_http_source_callback_runs_after_tokenization(monkeypatch):
    from martin.llm.deepseek_client import DeepSeekClient

    source = {"active": True}
    sent = []
    response = Mock()
    response.json.return_value = {"data": [{"total_tokens": 10}]}

    def post(url, **kwargs):
        if url.endswith("tokenization"):
            source["active"] = False
            return response
        sent.append(url)
        raise AssertionError("Revoked source reached model send")

    def check():
        if not source["active"]:
            raise ContextBudgetExceeded("memory_source_changed")

    monkeypatch.delenv("MARTIN_TOKENIZER_DISABLED", raising=False)
    monkeypatch.setattr("martin.llm.context_budget.requests.post", post)
    client = DeepSeekClient(
        api_key="synthetic-key",
        model="deepseek-v4.1-flash",
        base_url="https://ark.cn-beijing.volces.com/api/plan/v3",
    )
    check_token = begin_dispatch_check(check)
    try:
        with pytest.raises(ContextBudgetExceeded, match="记忆来源已变化"):
            client.chat([{"role": "user", "content": "合成病例问题"}])
        assert sent == []
        assert current_budget_scope() is None
    finally:
        finish_dispatch_check(check_token)


def test_t16_unavailable_dispatch_validator_fails_closed_without_private_text(
    monkeypatch,
):
    def check():
        raise OSError("synthetic-private-dispatch-canary")

    model = Mock(model_name="synthetic", max_tokens=512)
    check_token = begin_dispatch_check(check)
    token = begin_budget_scope("qa", policy=_policy())
    try:
        with pytest.raises(ContextBudgetExceeded) as exc:
            invoke_guarded(model, [HumanMessage(content="合成病例问题")])
        assert exc.value.reason == "source_validation_unavailable"
        assert "canary" not in str(exc.value)
        assert current_budget_scope().degraded
        model.invoke.assert_not_called()
    finally:
        finish_dispatch_check(check_token)
        finish_budget_scope(token)


def test_t16_format_repair_rechecks_sources_after_original_dispatch(monkeypatch):
    source = {"active": True}

    def check():
        if not source["active"]:
            raise ContextBudgetExceeded("memory_source_changed")

    token = begin_budget_scope("report", policy=_policy())
    check_token = begin_dispatch_check(check)
    finish_dispatch_check(check_token)
    source["active"] = False
    model = Mock(model_name="synthetic", max_tokens=512)
    try:
        with pytest.raises(ContextBudgetExceeded):
            invoke_guarded(
                model,
                [HumanMessage(content="待编辑答复")],
                revalidate_last_sources=True,
            )
        model.invoke.assert_not_called()
    finally:
        finish_budget_scope(token)


def test_t16_wrapped_format_repair_budget_failure_returns_public_degradation(
    monkeypatch,
):
    from martin.agent import agent as module
    from martin.agent.case_context import CaseContext

    executor = module.AgentExecutor.__new__(module.AgentExecutor)
    executor.thread_id, executor.verbose = "synthetic-repair-degradation", False
    executor.case_context = CaseContext()
    executor.report_preferences = {"conclusion_first": True}
    executor._agent = Mock()
    executor._agent.invoke.return_value = {
        "messages": [
            HumanMessage(content="生成报告"),
            AIMessage(content="原始报告答复", id="answer"),
        ]
    }

    def fail(*args, **kwargs):
        raise ContextBudgetExceeded("request_budget_exceeded")

    monkeypatch.setattr(module, "invoke_guarded", fail)
    monkeypatch.setattr(module, "get_chat_model", lambda: Mock())
    monkeypatch.setattr("martin.llm.context_budget.get_policy", lambda: _policy())
    result = executor.invoke({"input": "生成报告"})
    assert result["degraded"] and result["budget_trace"]["degraded"]
    assert "未完成完整分析" in result["output"]
    assert "不能据此作完整报告" in result["output"]
    assert not result["output"].startswith("错误: Agent 执行失败")
    saved = executor._agent.update_state.call_args_list[0].args[1]["messages"][0]
    assert saved.content == result["output"]


def test_t16_deadline_exhausted_by_tokenizer_never_sends_and_bounds_tokenizer_timeout(
    monkeypatch,
):
    from martin.llm.chat_model import BudgetedChatOpenAI

    model = BudgetedChatOpenAI(
        model="deepseek-v4.1-flash",
        api_key="synthetic-key",
        base_url="https://ark.cn-beijing.volces.com/api/plan/v3",
        max_tokens=512,
    )
    send = Mock()
    monkeypatch.setattr(model.client, "create", send)
    monkeypatch.delenv("MARTIN_TOKENIZER_DISABLED", raising=False)
    token = begin_budget_scope("qa", policy=_policy())
    scope = current_budget_scope()
    scope.started_at -= scope.policy.max_stage_seconds - 0.5
    response = Mock()
    response.json.return_value = {"data": [{"total_tokens": 20}]}

    def tokenize(*args, **kwargs):
        assert 0 < kwargs["timeout"] <= 0.5
        scope.started_at -= 1
        return response

    monkeypatch.setattr("martin.llm.context_budget.requests.post", tokenize)
    try:
        with pytest.raises(ContextBudgetExceeded) as exc:
            model.invoke([HumanMessage(content="合成输入")])
        assert exc.value.reason == "request_time_exceeded"
        send.assert_not_called()
    finally:
        finish_budget_scope(token)


def test_t16_report_fallback_logs_only_exception_types(monkeypatch, caplog):
    from martin.llm import chain

    marker = "synthetic-private-report-canary"

    def fail(*args, **kwargs):
        raise RuntimeError(marker)

    monkeypatch.setattr(chain, "search_by_detection", fail)
    with caplog.at_level(logging.WARNING, logger="martin.llm.chain"):
        assert (
            chain._build_knowledge_context({"nodules": []}, 1) == "暂无相关知识库资料。"
        )
        monkeypatch.setattr(chain, "create_diagnosis_chain", fail)
        monkeypatch.setattr(chain, "_generate_template_report", fail)
        chain.generate_report({"image": "synthetic", "nodules": [], "total_nodules": 0})
    assert marker not in caplog.text
    failures = [record for record in caplog.records if "失败:" in record.getMessage()]
    assert len(failures) == 3
    assert all(
        "RuntimeError" in record.getMessage() and record.exc_info is None
        for record in failures
    )


@pytest.mark.parametrize("transport", ["rest", "websocket"])
def test_t16_agent_budget_failures_are_explicit_public_answers(
    entity_client,
    entity_db,
    monkeypatch,
    transport,
):
    from martin.agent import agent as module
    from martin.agent.case_context import CaseContext
    from martin.services.thread_service import ThreadService

    assert (
        entity_client.post(
            "/api/auth/login",
            json={
                "username": "doctor_a",
                "password": "TestDoctorA!2026",
            },
        ).status_code
        == 200
    )
    thread = ThreadService(entity_db).create_thread("D001", "C002")

    def fail(*args, **kwargs):
        raise ContextBudgetExceeded(
            "summary_source_changed", omitted=["synthetic-summary"]
        )

    def factory(**kwargs):
        executor = module.AgentExecutor.__new__(module.AgentExecutor)
        executor.thread_id, executor.doctor_id, executor.verbose = thread, "D001", False
        executor.case_context = CaseContext()
        executor._agent = Mock()
        executor._agent.invoke.side_effect = fail
        return executor

    monkeypatch.setattr(module, "create_agent", factory)
    monkeypatch.setattr("martin.agent.audit.AuditLogger", lambda **kwargs: Mock())
    monkeypatch.setattr(
        "martin.agent.sessions.get_default_checkpointer", lambda: MemorySaver()
    )
    if transport == "rest":
        response = entity_client.post(
            "/api/agent/chat",
            json={
                "session_id": thread,
                "user_message": "生成报告",
            },
        )
        assert response.status_code == 200
        answer = response.json()["output"]
    else:
        with entity_client.websocket_connect(f"/api/ws/agent/{thread}") as websocket:
            assert websocket.receive_json()["type"] == "status"
            websocket.send_json({"message": "生成报告"})
            assert websocket.receive_json()["type"] == "status"
            event = websocket.receive_json()
            if event["type"] == "case_context":
                event = websocket.receive_json()
            assert event["type"] == "final"
            answer = event["content"]
    assert "摘要来源已变化" in answer
    assert "未完成完整分析" in answer and "不能据此作完整报告" in answer


def test_t16_sdk_retry_configuration_cannot_bypass_dispatch_guard():
    from martin.llm.chat_model import BudgetedChatOpenAI

    model = BudgetedChatOpenAI(
        model="deepseek-v4.1-flash",
        api_key="synthetic-key",
        base_url="https://ark.cn-beijing.volces.com/api/plan/v3",
        max_retries=3,
    )
    assert model.max_retries == 0
    assert model.root_client.max_retries == 0
    assert model.root_async_client.max_retries == 0


@pytest.fixture
def correction_dispatch_runtime(dispatch_runtime):
    from martin.memory.models import MemoryCandidate
    from martin.memory.router import MemoryRetrievalRouter
    from martin.memory.writer import MemoryWriter

    service, scope, _record, _context = dispatch_runtime
    writer = MemoryWriter(service, SimpleNamespace(sync=lambda *args, **kwargs: None))
    record = writer.write(
        scope,
        [
            MemoryCandidate(
                "correction",
                "医生更正陈述：结节直径9mm，业务8mm尚未核实",
                data={
                    "target_finding_id": "F002",
                    "field": "diameter_mm",
                    "proposed_value": 9.0,
                },
            )
        ],
        source_type="thread",
        source_id=scope.thread_id,
        provenance={
            "kind": "message",
            "actor_id": "D001",
            "actor_role": "doctor",
            "thread_id": scope.thread_id,
            "message_id": "synthetic-correction-source",
        },
    ).records[0]
    context = MemoryRetrievalRouter(service).retrieve(
        "D001", scope.thread_id, "生成报告", modes=[]
    )
    conflict = next(
        item
        for item in context.budget_items("生成报告")
        if item.reference.startswith("MEMORY CLAIM CONFLICTS:")
    )
    assert conflict.value["status"] == "conflict"
    assert service.get_record(scope, record["memory_id"])["status"] == "active"
    return service, scope, record, context, conflict


def test_t16_unchanged_correction_conflict_allows_provider_guard_after_tokenization(
    correction_dispatch_runtime,
    monkeypatch,
):
    from martin.llm.chat_model import BudgetedChatOpenAI

    _service, _scope, _record, context, conflict = correction_dispatch_runtime
    selected = context.budget_items("生成报告")
    model = BudgetedChatOpenAI(
        model="deepseek-v4.1-flash",
        api_key="synthetic-key",
        base_url="https://ark.cn-beijing.volces.com/api/plan/v3",
        max_tokens=512,
    )
    response = Mock()
    response.json.return_value = {"data": [{"total_tokens": 20}]}
    tokenizer = Mock(return_value=response)
    monkeypatch.delenv("MARTIN_TOKENIZER_DISABLED", raising=False)
    monkeypatch.setattr("martin.llm.context_budget.requests.post", tokenizer)
    token = begin_budget_scope("report", policy=_policy())
    check_token = begin_dispatch_check(
        lambda: validate_context_sources(context, selected, "生成报告")
    )
    try:
        payload = model._get_request_payload([HumanMessage(content=conflict.text())])
        assert "8.0" in payload["messages"][0]["content"]
        assert "9.0" in payload["messages"][0]["content"]
        assert tokenizer.call_count == 1
        assert current_budget_scope().calls == 1 and not current_budget_scope().degraded
    finally:
        finish_dispatch_check(check_token)
        finish_budget_scope(token)


@pytest.mark.parametrize("change", ["withdraw", "business_value"])
def test_t16_correction_conflict_guard_still_blocks_real_source_changes(
    correction_dispatch_runtime,
    entity_db,
    monkeypatch,
    change,
):
    from martin.db import transaction
    from martin.llm.chat_model import BudgetedChatOpenAI

    service, authorized, record, context, conflict = correction_dispatch_runtime
    response = Mock()
    response.json.return_value = {"data": [{"total_tokens": 20}]}

    def tokenize(*args, **kwargs):
        if change == "withdraw":
            service.retract_record(authorized, record["memory_id"])
        else:
            with transaction(entity_db) as connection:
                connection.execute("UPDATE findings SET diameter_mm=7 WHERE id='F002'")
        return response

    monkeypatch.delenv("MARTIN_TOKENIZER_DISABLED", raising=False)
    monkeypatch.setattr("martin.llm.context_budget.requests.post", tokenize)
    model = BudgetedChatOpenAI(
        model="deepseek-v4.1-flash",
        api_key="synthetic-key",
        base_url="https://ark.cn-beijing.volces.com/api/plan/v3",
        max_tokens=512,
    )
    token = begin_budget_scope("report", policy=_policy())
    check_token = begin_dispatch_check(
        lambda: validate_context_sources(context, [conflict], "生成报告")
    )
    try:
        with pytest.raises(ContextBudgetExceeded) as exc:
            model._get_request_payload([HumanMessage(content=conflict.text())])
        assert exc.value.reason == (
            "memory_source_changed"
            if change == "withdraw"
            else "conflict_source_changed"
        )
        assert current_budget_scope().calls == 0 and current_budget_scope().degraded
    finally:
        finish_dispatch_check(check_token)
        finish_budget_scope(token)


def test_t16_unchanged_correction_conflict_allows_direct_report_generation(
    correction_dispatch_runtime,
    monkeypatch,
):
    from langchain_core.runnables import RunnableLambda

    from martin.agent.report_scope import reset_report_scope, set_report_scope
    from martin.llm import chain
    from martin.services.report_input_service import ReportInputService

    service, authorized, _record, _context, _conflict = correction_dispatch_runtime
    calls = []
    model = RunnableLambda(
        lambda prompt: calls.append(prompt)
        or AIMessage(content="确认8mm，医生更正9mm待核实。")
    )
    monkeypatch.setattr(chain, "get_chat_model", lambda: model)
    monkeypatch.setattr(chain, "_build_knowledge_context", lambda *_: "暂无资料")
    scope_token = set_report_scope("D001", authorized.thread_id)
    token = begin_budget_scope("report", policy=_policy())
    try:
        evidence = ReportInputService(service.db_path).build(
            "D001", authorized.thread_id
        )
        result = chain.generate_report(evidence)
        assert result == "确认8mm，医生更正9mm待核实。"
        assert len(calls) == 1
        prompt = str(calls[0])
        assert (
            "MEMORY CLAIM CONFLICTS" in prompt
            and "business_value" in prompt
            and "proposed_value" in prompt
        )
        assert current_budget_scope().calls == 1 and not current_budget_scope().degraded
    finally:
        finish_budget_scope(token)
        reset_report_scope(scope_token)
