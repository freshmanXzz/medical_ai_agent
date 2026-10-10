"""Phase 1 regressions; no real model or patient data required."""
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from martin.agent.agent import AgentExecutor, CasePersistenceError, _build_system_prompt
from martin.agent.case_context import CaseContext
from martin.agent.tools import get_case_context, update_case_context


def executor():
    agent = AgentExecutor.__new__(AgentExecutor)
    agent.verbose = False
    agent.thread_id = "state-regression"
    agent.case_context = CaseContext()
    agent._agent = MagicMock()
    return agent


def test_only_current_turn_tools_are_returned_in_call_order():
    agent = executor()
    result = agent._parse_result([
        HumanMessage(content="old"),
        AIMessage(content="", tool_calls=[{"name": "old", "args": {}, "id": "old"}]),
        ToolMessage(content="old result", tool_call_id="old"),
        AIMessage(content="old answer"),
        HumanMessage(content="new"),
        AIMessage(content="", tool_calls=[
            {"name": "first", "args": {}, "id": "a"},
            {"name": "second", "args": {}, "id": "b"},
        ]),
        ToolMessage(content="second result", tool_call_id="b"),
        ToolMessage(content="first result", tool_call_id="a"),
        AIMessage(content="new answer"),
    ])
    assert result["output"] == "new answer"
    assert [(a.tool, output) for a, output in result["intermediate_steps"]] == [
        ("first", "first result"), ("second", "second result"),
    ]


def test_new_turn_without_tools_does_not_replay_history():
    result = executor()._parse_result([
        AIMessage(content="", tool_calls=[{"name": "old", "args": {}, "id": "old"}]),
        ToolMessage(content="old result", tool_call_id="old"),
        HumanMessage(content="hello"),
        AIMessage(content="hello back"),
    ])
    assert result["intermediate_steps"] == []


def test_unrelated_tool_result_is_not_assigned_to_current_call():
    result = executor()._parse_result([
        HumanMessage(content="current"),
        AIMessage(content="", tool_calls=[{"name": "current", "args": {}, "id": "current-id"}]),
        ToolMessage(content="unrelated result", tool_call_id="different-id"),
    ])
    assert result["intermediate_steps"][0][1] == ""


def test_runtime_tool_update_is_not_overwritten_by_graph_input_snapshot():
    agent = executor()

    def invoke(state, config):
        update_case_context.invoke({"user_input": "患者 62 岁"})
        assert get_case_context().patient_info["age"] == 62
        assert "62" in _build_system_prompt({"case_context": get_case_context().to_dict()})
        return {"case_context": state["case_context"], "messages": [AIMessage(content="done")]}

    agent._agent.invoke.side_effect = invoke
    agent.invoke({"input": "患者 62 岁"})
    assert agent.case_context.patient_info["age"] == 62
    saved = agent._agent.update_state.call_args.args[1]["case_context"]
    assert CaseContext.from_dict(saved).patient_info["age"] == 62


def test_save_failure_is_not_success():
    agent = executor()
    agent._agent.update_state.side_effect = OSError("disk full")
    agent._agent.invoke.return_value = {"messages": [AIMessage(content="done")]}
    with pytest.raises(CasePersistenceError, match="病例保存失败"):
        agent.invoke({"input": "hello"})


@pytest.mark.parametrize(
    "tool_name",
    [
        "save_long_term_memory",
        "save_report_preference",
        "retract_long_term_memory",
    ],
)
def test_memory_mutation_refreshes_next_model_prompt(monkeypatch, tool_name):
    from types import SimpleNamespace

    from martin.agent.agent import _case_context_prompt, _memory_prompt_var
    from martin.agent.report_scope import reset_report_scope, set_report_scope
    from martin.memory.interaction import (
        MemoryInteraction,
        reset_interaction,
        set_interaction,
    )

    router = MagicMock()
    router.retrieve.return_value.to_prompt.return_value = "CURRENT MEMORY STATE"
    monkeypatch.setattr("martin.memory.router.MemoryRetrievalRouter", lambda: router)
    request = SimpleNamespace(
        state={
            "messages": [
                HumanMessage(content="withdraw", id="real-message"),
                AIMessage(
                    content="", tool_calls=[{"id": "m", "name": tool_name, "args": {}}]
                ),
                ToolMessage(content="completed", tool_call_id="m"),
            ]
        },
        override=lambda **kwargs: SimpleNamespace(**kwargs),
    )
    actor = set_report_scope("doctor", "thread")
    interaction = set_interaction(MemoryInteraction("real-message", "withdraw"))
    memory = _memory_prompt_var.set("STALE MEMORY STATE")
    try:
        prompt = _case_context_prompt.wrap_model_call(
            request, lambda req: req.system_message.content
        )
    finally:
        _memory_prompt_var.reset(memory)
        reset_interaction(interaction)
        reset_report_scope(actor)
    assert "CURRENT MEMORY STATE" in prompt
    assert "STALE MEMORY STATE" not in prompt
    router.retrieve.assert_called_once_with("doctor", "thread", "withdraw")


def test_execution_logger_never_writes_tool_text(monkeypatch):
    from martin.agent.agent import AgentLoggingHandler

    log = MagicMock()
    monkeypatch.setattr("martin.agent.agent._get_thinking_logger", lambda: log)
    handler = AgentLoggingHandler()
    handler.on_tool_start(
        {"name": "generate_report"},
        {
            "reasoning": "private reasoning",
            "patient": "private patient",
        },
    )
    handler.on_tool_end("private report")
    assert "private" not in str(log.mock_calls)
    assert "tool_completed" in str(log.mock_calls)


def test_case_tool_logs_no_user_input(caplog):
    from martin.agent.tools import reset_case_context, set_case_context

    token = set_case_context(CaseContext())
    try:
        with caplog.at_level("INFO", logger="martin.agent.tools"):
            update_case_context.invoke({"user_input": "synthetic-private-canary"})
    finally:
        reset_case_context(token)
    assert "update_case_context" in caplog.text
    assert "synthetic-private-canary" not in caplog.text


def test_knowledge_tool_logs_no_query_or_provider_exception(monkeypatch, caplog):
    from martin.agent import tools

    monkeypatch.setattr(tools, "get_vector_store", lambda: object())

    def fail_search(*args, **kwargs):
        raise RuntimeError("synthetic-private-exception-canary")

    monkeypatch.setattr(tools, "search_by_query", fail_search)
    with caplog.at_level("INFO", logger="martin.agent.tools"):
        result = tools.retrieve_knowledge.invoke(
            {"query": "synthetic-private-query-canary"}
        )
    assert "错误:" in result
    assert "RuntimeError" in caplog.text
    assert "synthetic-private" not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)
