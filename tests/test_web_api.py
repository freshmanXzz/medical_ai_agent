"""Web API 的轻量集成测试，不调用真实模型或外部 LLM。"""

from pathlib import Path

import pytest

from fastapi.testclient import TestClient

from api.main import app


def test_health_endpoint():
    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_knowledge_search_returns_raw_vector_results(monkeypatch):
    from martin.rag.knowledge_manager import KnowledgeManager

    monkeypatch.setattr(
        KnowledgeManager,
        "search_raw_vectors",
        lambda self, query, top_k: [
            {
                "rank": 1,
                "score": 0.88,
                "source": "guide.md",
                "source_type": "builtin",
                "document_id": "builtin:guide.md",
                "content": "肺结节随访建议",
            }
        ],
    )

    with TestClient(app) as client:
        response = client.post("/api/knowledge/search", json={"query": "肺结节随访"})

    assert response.status_code == 200
    assert response.json() == {
        "query": "肺结节随访",
        "total": 1,
        "results": [{
            "rank": 1,
            "score": 0.88,
            "source": "guide.md",
            "source_type": "builtin",
            "document_id": "builtin:guide.md",
            "content": "肺结节随访建议",
        }],
    }


def test_knowledge_search_rejects_blank_query():
    with TestClient(app) as client:
        response = client.post("/api/knowledge/search", json={"query": "   "})

    assert response.status_code == 400
    assert response.json()["detail"] == "检索文本不能为空"


def test_knowledge_search_reports_unavailable_vector_store(monkeypatch):
    from martin.rag.knowledge_manager import KnowledgeManager, VectorStoreUnavailableError

    def raise_unavailable(self, query, top_k):
        raise VectorStoreUnavailableError("向量库尚未初始化，请先重建知识库向量")

    monkeypatch.setattr(KnowledgeManager, "search_raw_vectors", raise_unavailable)

    with TestClient(app) as client:
        response = client.post("/api/knowledge/search", json={"query": "肺结节"})

    assert response.status_code == 503
    assert "尚未初始化" in response.json()["detail"]


def test_missing_image_returns_404_before_model_load():
    with TestClient(app) as client:
        response = client.post(
            "/api/image/analyze",
            json={
                "image_path": "data/not-present-for-web-test.nii.gz",
                "session_id": "web-test",
            },
        )

    assert response.status_code == 404
    assert "图像文件不存在" in response.json()["detail"]


def test_detection_keeps_session_case_context(monkeypatch, tmp_path):
    import martin.agent.agent as agent_module
    import martin.agent.tools as tools_module
    from martin.agent.case_context import CaseContext

    image_path = tmp_path / "case.nii.gz"
    image_path.write_bytes(b"test")
    case_context = CaseContext.from_dict({"patient_info": {"age": 62, "gender": "男"}})

    # AgentExecutor._context_cache 已移除，CaseContext 现通过 LangGraph state_schema + Checkpointer 管理。
    # 此处通过替换 create_agent 返回携带预设 case_context 的桩对象，模拟"从 checkpoint 恢复"的场景。
    class _StubAgent:
        """仅暴露 case_context 属性，供 image 路由读取并注入到 ContextVar。"""

        def __init__(self, ctx):
            self.case_context = ctx
            self.saved = False

        def save_case_context(self):
            self.saved = True

    stub_agent = _StubAgent(case_context)
    monkeypatch.setattr(
        agent_module,
        "create_agent",
        lambda **kwargs: stub_agent,
    )
    image_path_obj = image_path

    def fake_analyze(image_path, reasoning=""):
        assert image_path == str(image_path_obj)
        assert reasoning == ""
        tools_module.get_case_context().update_from_detection({
            "image": str(image_path_obj),
            "nodules": [{
                "index": 1,
                "diameter": 8.2,
                "score": 0.91,
                "center": {"x": 1, "y": 2, "z": 3},
                "dimensions": {"width": 8.2, "height": 7.1, "depth": 6.0},
            }],
        })
        return (
            "图像: case.nii.gz\n检测到结节总数: 1 个\n\n"
            "结节 1:\n"
            "  - 最大直径: 8.20 mm\n"
            "  - 检测置信度: 0.9100 (91.00%)\n"
            "  - 中心位置: (1.00, 2.00, 3.00) mm\n"
            "  - 三维尺寸: 8.20 x 7.10 x 6.00 mm\n"
        )

    monkeypatch.setattr(tools_module.analyze_image, "func", fake_analyze)

    with TestClient(app) as client:
        response = client.post(
            "/api/image/analyze",
            json={"image_path": str(image_path), "session_id": "detection-session"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_nodules"] == 1
    assert payload["case_context"]["patient_info"]["age"] == 62
    assert len(payload["case_context"]["nodules"]) == 1
    assert stub_agent.saved is True


def test_chat_endpoint_calls_agent_and_returns_context(monkeypatch):
    import martin.agent.agent as agent_module

    class FakeAgent:
        case_context = None

        def invoke(self, inputs):
            assert inputs == {"input": "你好"}
            return {"output": "你好，我是 Martin。", "intermediate_steps": []}

    monkeypatch.setattr(agent_module, "create_agent", lambda **_: FakeAgent())

    with TestClient(app) as client:
        response = client.post(
            "/api/agent/chat",
            json={
                "session_id": "web-chat-test",
                "user_message": "你好",
                "case_context": {"patient_info": {"age": 60}},
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["output"] == "你好，我是 Martin。"
    assert payload["session_id"] == "web-chat-test"
    assert payload["case_context"]["patient_info"]["age"] == 60


def test_spa_history_route_returns_frontend_when_built():
    if not Path("frontend/dist/index.html").is_file():
        pytest.skip("前端尚未构建")
    with TestClient(app) as client:
        response = client.get("/workspace")

    assert response.status_code == 200
    assert "Martin 医学智能体" in response.text


def test_chat_endpoint_writes_audit_log(monkeypatch, tmp_path):
    """测试 /api/agent/chat 端点在 Agent 执行后正确写入审计日志。"""
    import martin.agent.agent as agent_module
    import martin.agent.audit as audit_module
    from langchain_core.agents import AgentAction

    # 用列表捕获 StubAuditLogger 实例，便于断言其属性
    instances = []

    class _StubAuditLogger:
        """记录 log_tool_call 调用参数的桩对象。"""

        def __init__(self, session_id=None, audit_dir=None):
            self.session_id = session_id
            self.log_file = str(tmp_path / f"{session_id}_test.jsonl")
            self.logged_calls = []

        def log_tool_call(
            self,
            tool_name,
            args,
            output_summary,
            user_input="",
            final_output="",
        ):
            self.logged_calls.append({
                "tool_name": tool_name,
                "args": args,
                "output_summary": output_summary,
                "user_input": user_input,
                "final_output": final_output,
            })

        def log_agent_error(self, error_msg):
            pass

    def _make_stub_logger(session_id=None, audit_dir=None):
        inst = _StubAuditLogger(session_id=session_id, audit_dir=audit_dir)
        instances.append(inst)
        return inst

    monkeypatch.setattr(audit_module, "AuditLogger", _make_stub_logger)

    class FakeAgent:
        """返回带一个 intermediate_step 的 Agent 桩。"""

        case_context = None

        def invoke(self, inputs):
            action = AgentAction(
                tool="retrieve_knowledge",
                tool_input={"query": "8mm结节", "reasoning": "知识问题"},
                log="",
            )
            return {
                "output": "根据 Lung-RADS...",
                "intermediate_steps": [(action, "Lung-RADS v2022...")],
            }

    monkeypatch.setattr(agent_module, "create_agent", lambda **_: FakeAgent())

    with TestClient(app) as client:
        response = client.post(
            "/api/agent/chat",
            json={
                "session_id": "audit-test-session",
                "user_message": "8mm结节怎么办",
            },
        )

    assert response.status_code == 200
    assert len(instances) == 1
    assert instances[0].session_id == "audit-test-session"
    assert len(instances[0].logged_calls) == 1
    call = instances[0].logged_calls[0]
    assert call["tool_name"] == "retrieve_knowledge"
    assert call["user_input"] == "8mm结节怎么办"
    assert call["final_output"] == "根据 Lung-RADS..."
