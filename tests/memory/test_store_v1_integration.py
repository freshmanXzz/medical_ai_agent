"""Cross-thread Store-to-Prompt-to-answer and failure-path integration."""

import logging

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.sqlite import SqliteSaver
from pydantic import PrivateAttr

from martin.db import transaction
from martin.agent.sessions import SessionManager
from martin.memory.namespaces import patient_memory_ns
from martin.memory.service import MemoryService
from martin.memory.store import get_default_store


class PromptAwareModel(BaseChatModel):
    _prompts: list[str] = PrivateAttr(default_factory=list)

    @property
    def _llm_type(self):
        return "memory-v1-scripted"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        prompt = next(
            message.content
            for message in messages
            if isinstance(message, SystemMessage)
        )
        self._prompts.append(prompt)
        question = next(
            message.content for message in reversed(messages)
            if isinstance(message, HumanMessage)
        )
        if "以后报告" in question and not any(
            isinstance(message, ToolMessage) for message in messages
        ):
            message = AIMessage(
                content="",
                tool_calls=[{
                    "name": "save_report_preference",
                    "args": {
                        "conclusion_first": True,
                        "max_words": 200,
                        "focus": ["毛刺征"],
                    },
                    "id": "call-report-style",
                }],
            )
            return ChatResult(generations=[ChatGeneration(message=message)])
        if "以后报告" in question:
            answer = "报告偏好已保存。"
        elif "store_unavailable" in prompt:
            answer = "当前结节 8mm。历史记忆不可用，无法可靠比较本次与既往变化。"
        elif "上次" in question and '"finding_id": "F001"' in prompt:
            answer = "历史 6mm，本次 8mm，增加 2mm；仍需医生结合原始影像判断。"
        else:
            answer = "结论：重点观察毛刺征；报告保持简短。"
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=answer))]
        )


def _login(client, doctor="a"):
    response = client.post(
        "/api/auth/login",
        json={
            "username": f"doctor_{doctor}",
            "password": f"TestDoctor{doctor.upper()}!2026",
        },
    )
    assert response.status_code == 200


def _thread(client, case_id):
    response = client.post("/api/threads", json={"case_id": case_id})
    assert response.status_code == 200
    return response.json()["thread_id"]


def _receive_final(ws):
    for _ in range(12):
        event = ws.receive_json()
        assert event["type"] != "error", event
        if event["type"] == "final":
            return event["content"]
    raise AssertionError("WebSocket did not deliver a final answer")


def _use_model_and_saver(monkeypatch, saver, model, tmp_path):
    from martin.agent.audit import AuditLogger

    monkeypatch.setattr("martin.agent.agent.get_chat_model", lambda: model)
    monkeypatch.setattr(
        "martin.agent.agent._get_thinking_logger",
        lambda: logging.getLogger("memory-v1-test"),
    )
    monkeypatch.setattr(
        "martin.agent.sessions.get_default_checkpointer", lambda: saver
    )
    original_init = AuditLogger.__init__

    def isolated_audit(self, session_id=None, audit_dir=None):
        original_init(self, session_id, str(tmp_path / "audit"))

    monkeypatch.setattr(AuditLogger, "__init__", isolated_audit)


def test_demo_a_preference_reaches_new_thread_prompt_and_answer(
    entity_client, tmp_path, monkeypatch
):
    model = PromptAwareModel()
    with SqliteSaver.from_conn_string(str(tmp_path / "sessions.sqlite")) as saver:
        _use_model_and_saver(monkeypatch, saver, model, tmp_path)
        _login(entity_client)
        first_thread = _thread(entity_client, "C001")
        response = entity_client.post(
            "/api/agent/chat",
            json={
                "session_id": first_thread,
                "user_message": "以后报告结论放前面，200字以内，重点写毛刺征",
            },
        )
        assert response.status_code == 200
        assert "已保存" in response.json()["output"]
        assert get_default_store().get(
            ("doctor", "D001", "preferences"), "report_style"
        ) is not None
        second_thread = _thread(entity_client, "C001")
        assert first_thread != second_thread
        response = entity_client.post(
            "/api/agent/chat",
            json={"session_id": second_thread, "user_message": "生成简短报告"},
        )
        assert response.status_code == 200
        assert response.json()["output"].startswith("结论：")
        assert "毛刺征" in response.json()["output"]
        assert '"max_words": 200' in model._prompts[-1]
        assert '"毛刺征"' in model._prompts[-1]
        assert "[DOCTOR OUTPUT PREFERENCES — MUST FOLLOW]" in model._prompts[-1]
        assert "不超过 200 个字符" in model._prompts[-1]

        _login(entity_client, "b")
        other_thread = _thread(entity_client, "C003")
        response = entity_client.post(
            "/api/agent/chat",
            json={"session_id": other_thread, "user_message": "生成报告"},
        )
        assert response.status_code == 200
        assert '"毛刺征"' not in model._prompts[-1]


def test_demo_b_historical_store_and_current_case_are_separate(
    entity_client, tmp_path, monkeypatch
):
    model = PromptAwareModel()
    with SqliteSaver.from_conn_string(str(tmp_path / "sessions.sqlite")) as saver:
        _use_model_and_saver(monkeypatch, saver, model, tmp_path)
        _login(entity_client)
        _thread(entity_client, "C001")
        current_thread = _thread(entity_client, "C002")
        response = entity_client.post(
            "/api/agent/chat",
            json={"session_id": current_thread, "user_message": "和上次相比结节变化多少？"},
        )
        assert response.status_code == 200
        assert "6mm" in response.json()["output"]
        assert "8mm" in response.json()["output"]
        assert "2mm" in response.json()["output"]
        prompt = model._prompts[-1]
        current_section = prompt.split("[CURRENT CASE FACTS]", 1)[1].split(
            "[DOCTOR PREFERENCES]", 1
        )[0]
        historical_section = prompt.split("[PATIENT HISTORICAL MEMORY]", 1)[1].split(
            "[CASE MEMORY]", 1
        )[0]
        assert '"finding_id": "F002"' in current_section
        assert '"finding_id": "F001"' not in current_section
        assert '"finding_id": "F001"' in historical_section
        assert '"finding_id": "F002"' not in historical_section
        assert get_default_store().get(patient_memory_ns("P001"), "observation:F001")


def test_store_read_failure_does_not_abort_agent(
    entity_client, tmp_path, monkeypatch
):
    def fail_store(_self):
        raise OSError("synthetic memory database failure")

    monkeypatch.setattr(MemoryService, "_store", fail_store)
    model = PromptAwareModel()
    with SqliteSaver.from_conn_string(str(tmp_path / "sessions.sqlite")) as saver:
        _use_model_and_saver(monkeypatch, saver, model, tmp_path)
        _login(entity_client)
        thread_id = _thread(entity_client, "C002")
        response = entity_client.post(
            "/api/agent/chat",
            json={"session_id": thread_id, "user_message": "分析当前病例"},
        )
        assert response.status_code == 200
        assert "历史记忆不可用" in model._prompts[-1]
        assert '"finding_id": "F002"' in model._prompts[-1]
        prior_calls = len(model._prompts)
        response = entity_client.post(
            "/api/agent/chat",
            json={"session_id": thread_id, "user_message": "和上次相比变大了吗？"},
        )
        assert response.status_code == 200
        assert "无法可靠比较" in response.json()["output"]
        assert "8mm" in response.json()["output"]
        assert len(model._prompts) == prior_calls + 1
        with entity_client.websocket_connect(f"/api/ws/agent/{thread_id}") as ws:
            assert ws.receive_json()["type"] == "status"
            ws.send_json({"message": "和上次相比变大了吗？"})
            assert ws.receive_json()["type"] == "status"
            answer = _receive_final(ws)
            assert "无法可靠比较" in answer
            assert "8mm" in answer
        assert len(model._prompts) == prior_calls + 2


def test_superseded_business_finding_is_removed_from_store(entity_db, tmp_path):
    from martin.services.thread_service import ThreadService

    thread_id = ThreadService(entity_db).create_thread("D001", "C002")
    from langgraph.store.sqlite import SqliteStore

    with SqliteStore.from_conn_string(str(tmp_path / "memory.sqlite")) as store:
        store.setup()
        service = MemoryService(entity_db, store)
        assert service.snapshot_for_thread("D001", thread_id).historical_observations
        assert store.get(patient_memory_ns("P001"), "observation:F001")
        with transaction(entity_db) as connection:
            connection.execute(
                "UPDATE findings SET status = 'superseded' WHERE id = 'F001'"
            )
        assert (
            service.snapshot_for_thread("D001", thread_id).historical_observations
            == []
        )
        assert store.get(patient_memory_ns("P001"), "observation:F001") is None


def test_explicit_preference_endpoint_uses_authenticated_doctor(entity_client):
    _login(entity_client)
    response = entity_client.post(
        "/api/memory/preferences/report-style",
        json={"conclusion_first": True, "max_words": 180, "focus": ["毛刺征"]},
    )
    assert response.status_code == 200
    assert entity_client.get("/api/memory/preferences/report-style").json()[
        "max_words"
    ] == 180
    _login(entity_client, "b")
    assert entity_client.get("/api/memory/preferences/report-style").json() == {}


def test_store_write_failure_does_not_claim_saved(
    entity_client, tmp_path, monkeypatch
):
    def fail_save(_self, _doctor_id, _key, _value):
        raise OSError("synthetic store write failure")

    monkeypatch.setattr(MemoryService, "save_doctor_preference", fail_save)
    model = PromptAwareModel()
    with SqliteSaver.from_conn_string(str(tmp_path / "sessions.sqlite")) as saver:
        _use_model_and_saver(monkeypatch, saver, model, tmp_path)
        _login(entity_client)
        thread_id = _thread(entity_client, "C001")
        response = entity_client.post(
            "/api/agent/chat",
            json={"session_id": thread_id, "user_message": "以后报告结论放前面"},
        )
        assert response.status_code == 200
        answer = response.json()["output"]
        assert "保存失败" in answer
        assert "后续会话可能无法自动恢复" in answer
        assert "本次偏好仅临时使用" in answer
        assert "偏好已保存" not in answer
        assert SessionManager(saver).get_messages(thread_id)[-1].content == answer
        assert get_default_store().get(
            ("doctor", "D001", "preferences"), "report_style"
        ) is None
        ws_thread = _thread(entity_client, "C001")
        with entity_client.websocket_connect(f"/api/ws/agent/{ws_thread}") as ws:
            assert ws.receive_json()["type"] == "status"
            ws.send_json({"message": "以后报告结论放前面"})
            assert ws.receive_json()["type"] == "status"
            answer = _receive_final(ws)
            assert "保存失败" in answer
            assert "后续会话可能无法自动恢复" in answer
            assert "偏好已保存" not in answer
        assert SessionManager(saver).get_messages(ws_thread)[-1].content == answer


def test_longitudinal_question_does_not_invent_history_when_store_down(
    entity_client, tmp_path, monkeypatch
):
    """A scripted model verifies the degradation contract, not live reasoning."""
    model = PromptAwareModel()
    with SqliteSaver.from_conn_string(str(tmp_path / "sessions.sqlite")) as saver:
        _use_model_and_saver(monkeypatch, saver, model, tmp_path)
        _login(entity_client)
        thread_id = _thread(entity_client, "C002")
        store = get_default_store()
        prior = entity_client.post(
            "/api/agent/chat",
            json={"session_id": thread_id, "user_message": "和上次相比变化多少"},
        )
        assert prior.status_code == 200
        assert "6mm" in prior.json()["output"]

        def fail_search(*args, **kwargs):
            raise OSError("synthetic store read failure")

        monkeypatch.setattr(store, "search", fail_search)
        response = entity_client.post(
            "/api/agent/chat",
            json={"session_id": thread_id, "user_message": "和上次相比有没有变化"},
        )
        assert response.status_code == 200
        assert len(model._prompts) == 2
        prompt = model._prompts[-1]
        assert "[MEMORY STATUS]" in prompt
        assert "store_unavailable" in prompt
        assert "不得推断或编造既往测量值" in prompt
        assert "不得声称无变化" in prompt
        assert '"finding_id": "F002"' in prompt
        assert '"finding_id": "F001"' not in prompt
        answer = response.json()["output"]
        assert "历史记忆不可用" in answer
        assert "无法可靠比较" in answer
        assert "8mm" in answer
        assert "6mm" not in answer
        assert "无变化" not in answer
