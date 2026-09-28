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
