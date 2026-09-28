"""Real LangGraph/SQLite tests with scripted model and synthetic CT findings.

Only the external LLM and detector are replaced; graph execution, tool routing,
checkpoint writes, HTTP and WebSocket adapters run production code.
"""
import logging
import sqlite3
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.sqlite import SqliteSaver
from pydantic import PrivateAttr

from martin.agent.agent import AgentExecutor
from martin.agent.errors import CasePersistenceError
from martin.agent.tools import analyze_image, update_case_context


class ScriptedModel(BaseChatModel):
    """Capture actual model inputs without making any network requests."""

    _responses: list = PrivateAttr(default_factory=list)
    _inputs: list = PrivateAttr(default_factory=list)

    @property
    def _llm_type(self):
        return "phase1-scripted"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self._inputs.append(list(messages))
        if not self._responses:
            raise AssertionError("Unexpected extra model invocation")
        return ChatResult(generations=[ChatGeneration(message=self._responses.pop(0))])


def model_with(*responses):
    model = ScriptedModel()
    model._responses = list(responses)
    return model


def tool_call(name, args, call_id="call-current"):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


@pytest.fixture(autouse=True)
def isolate_logs(monkeypatch, tmp_path):
    import martin.agent.agent as module
    from martin.agent.audit import AuditLogger

    monkeypatch.setattr(module, "_get_thinking_logger", lambda: logging.getLogger("phase1-test"))
    original_init = AuditLogger.__init__

    def init(self, session_id=None, audit_dir=None):
        original_init(self, session_id, str(tmp_path / "audit"))

    monkeypatch.setattr(AuditLogger, "__init__", init)


def use_model(monkeypatch, model):
    monkeypatch.setattr("martin.agent.agent.get_chat_model", lambda: model)


def test_sqlite_restart_recovers_tool_update_and_continues_chat(monkeypatch, tmp_path):
    path = str(tmp_path / "sessions.sqlite")
    use_model(monkeypatch, model_with(
        tool_call("update_case_context", {"user_input": "患者62岁"}),
        AIMessage(content="updated"),
    ))
    with SqliteSaver.from_conn_string(path) as saver:
        agent = AgentExecutor([update_case_context], False, "patient-a", saver)
        result = agent.invoke({"input": "患者62岁"})
        assert result["output"] == "updated"
        assert len(result["intermediate_steps"]) == 1
        assert agent.case_context.patient_info["age"] == 62
    del agent

    use_model(monkeypatch, model_with(AIMessage(content="follow-up")))
    with SqliteSaver.from_conn_string(path) as saver:
        restored = AgentExecutor([update_case_context], False, "patient-a", saver)
        assert restored.case_context.patient_info["age"] == 62
        result = restored.invoke({"input": "继续"})
        assert result["output"] == "follow-up"
        assert result["intermediate_steps"] == []
        isolated = AgentExecutor([update_case_context], False, "patient-b", saver)
        assert isolated.case_context.patient_info["age"] is None


def test_next_model_prompt_sees_tool_update_in_same_turn(monkeypatch, tmp_path):
    model = model_with(
        tool_call("update_case_context", {"user_input": "患者62岁"}),
        AIMessage(content="done"),
    )
    use_model(monkeypatch, model)
    with SqliteSaver.from_conn_string(str(tmp_path / "prompt.sqlite")) as saver:
        result = AgentExecutor([update_case_context], False, "prompt", saver).invoke(
            {"input": "患者62岁，请结合年龄分析"}
        )
    assert result["output"] == "done"
    assert len(model._inputs) == 2
    first = next(m.content for m in model._inputs[0] if isinstance(m, SystemMessage))
    second = next(m.content for m in model._inputs[1] if isinstance(m, SystemMessage))
    assert "【当前病例上下文】" not in first
    assert "年龄：62 岁" in second.split("【当前病例上下文】", 1)[1]


@pytest.mark.parametrize("has_nodule", [True, False])
def test_analyze_image_survives_sqlite_restart(monkeypatch, tmp_path, has_nodule):
    import martin.agent.tools as tools_module

    nodules = [{"index": 1, "diameter": 8.2, "score": 0.95}] if has_nodule else []
    detector = MagicMock()
    detector.detect.return_value = {
        "image": "synthetic.nii.gz", "total_nodules": len(nodules), "nodules": nodules,
    }
    monkeypatch.setattr(tools_module, "_get_nodule_detector", lambda: detector)
    use_model(monkeypatch, model_with(
        tool_call("analyze_image", {"image_path": "synthetic.nii.gz"}),
        AIMessage(content="analyzed"),
    ))
    path = str(tmp_path / "ct.sqlite")
    with SqliteSaver.from_conn_string(path) as saver:
        result = AgentExecutor([analyze_image], False, "ct", saver).invoke({"input": "分析影像"})
        assert result["output"] == "analyzed"
    with SqliteSaver.from_conn_string(path) as saver:
        restored = AgentExecutor([analyze_image], False, "ct", saver)
        assert restored.case_context.nodules == nodules
        assert restored.case_context.detection_completed is True
        assert restored.case_context.image_info["image_name"] == "synthetic.nii.gz"


@pytest.mark.parametrize("failure_point", ["graph", "final_save"])
def test_rest_and_websocket_reject_checkpoint_failure(
    monkeypatch, tmp_path, failure_point, entity_db
):
    from api.main import app
    import martin.agent.agent as agent_module
    import martin.agent.sessions as sessions_module

    path = str(tmp_path / "failure.sqlite")
    with SqliteSaver.from_conn_string(path) as saver:
        saver.setup()
        monkeypatch.setattr(sessions_module, "get_default_checkpointer", lambda: saver)
        original_factory = agent_module.create_agent
        use_model(monkeypatch, model_with(AIMessage(content="not saved"), AIMessage(content="not saved")))

        def fail(*args, **kwargs):
            raise sqlite3.OperationalError("synthetic disk write failure")

        if failure_point == "graph":
            monkeypatch.setattr(saver, "put", fail)

        def create(**kwargs):
            agent = original_factory(tools=[], **kwargs)
            if failure_point == "final_save":
                monkeypatch.setattr(agent._agent, "update_state", fail)
            return agent

        monkeypatch.setattr(agent_module, "create_agent", create)
        with TestClient(app) as client:
            assert client.post(
                "/api/auth/login",
                json={"username": "doctor_a", "password": "TestDoctorA!2026"},
            ).status_code == 200
            rest_thread = client.post("/api/threads", json={"case_id": "C001"}).json()[
                "thread_id"
            ]
            ws_thread = client.post("/api/threads", json={"case_id": "C001"}).json()[
                "thread_id"
            ]
            response = client.post(
                "/api/agent/chat", json={"session_id": rest_thread, "user_message": "hello"}
            )
            assert response.status_code in (502, 503)
            assert "output" not in response.json()
            with client.websocket_connect(f"/api/ws/agent/{ws_thread}") as ws:
                assert ws.receive_json()["type"] == "status"
                ws.send_json({"message": "hello"})
                events = [ws.receive_json(), ws.receive_json()]
                assert events[-1]["type"] == "error"
                assert all(e["type"] != "final" for e in events)
                # A sentinel request proves that no delayed success final was queued.
                ws.send_json({"message": ""})
                sentinel = ws.receive_json()
                assert sentinel["type"] == "error"
                assert sentinel["content"] == "消息为空"


def test_final_save_failure_raises_controlled_exception(monkeypatch, tmp_path):
    use_model(monkeypatch, model_with(AIMessage(content="not saved")))
    with SqliteSaver.from_conn_string(str(tmp_path / "write.sqlite")) as saver:
        agent = AgentExecutor([], False, "write", saver)

        def fail(*args, **kwargs):
            raise sqlite3.OperationalError("synthetic disk full")

        monkeypatch.setattr(agent._agent, "update_state", fail)
        with pytest.raises(CasePersistenceError):
            agent.invoke({"input": "hello"})
