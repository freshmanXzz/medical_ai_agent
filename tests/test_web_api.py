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


def test_analyze_rejects_a_session_without_a_server_side_image_source():
    with TestClient(app) as client:
        response = client.post(
            "/api/image/analyze",
            json={"session_id": "web-test"},
        )

    assert response.status_code == 409
    assert "请先上传" in response.json()["detail"]


def test_upload_and_analyze_keep_object_reference_server_side(monkeypatch, tmp_path):
    import api.routers.image as image_router
    import martin.agent.tools as tools_module
    import martin.utils.oss_client as oss_client
    from martin.agent.case_context import CaseContext

    downloaded = tmp_path / "downloaded.nii.gz"
    downloaded.write_bytes(b"test")
    case_context = CaseContext.from_dict({"patient_info": {"age": 62, "gender": "男"}})

    class _StubAgent:
        def __init__(self, ctx):
            self.case_context = ctx
            self.saved = False

        def save_case_context(self):
            self.saved = True

    stub_agent = _StubAgent(case_context)
    monkeypatch.setattr(image_router, "_create_session_agent", lambda _: stub_agent)

    class FakeOss:
        def upload_file(self, path):
            return "ct/study-123.nii.gz"

        def download_file(self, object_name):
            assert object_name == "ct/study-123.nii.gz"
            return str(downloaded)

    monkeypatch.setattr(oss_client, "get_oss_client", lambda: FakeOss())

    def fake_analyze(image_path, reasoning=""):
        assert image_path == str(downloaded)
        assert reasoning == ""
        tools_module.get_case_context().update_from_detection({
            "image": str(downloaded),
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
        upload = client.post(
            "/api/image/upload",
            data={"session_id": "detection-session"},
            files={"file": ("patient-study.nii.gz", b"nifti-data", "application/octet-stream")},
        )
        response = client.post("/api/image/analyze", json={"session_id": "detection-session"})

    assert upload.status_code == 200
    assert upload.json() == {"size": len(b"nifti-data"), "filename": "patient-study.nii.gz"}
    assert "object_name" not in upload.text
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_nodules"] == 1
    assert payload["case_context"]["patient_info"]["age"] == 62
    assert len(payload["case_context"]["nodules"]) == 1
    assert "object_name" not in response.text
    assert "image_path" not in response.text
    assert "ct/study-123.nii.gz" not in response.text
    assert stub_agent.case_context.image_info["object_name"] == "ct/study-123.nii.gz"
    assert stub_agent.case_context.image_info["image_path"] == "ct/study-123.nii.gz"
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


def test_chat_attachment_does_not_accept_or_echo_an_object_key(monkeypatch):
    import martin.agent.agent as agent_module

    class FakeAgent:
        case_context = None

        def invoke(self, inputs):
            assert "patient-study.nii.gz" in inputs["input"]
            assert "ct/private-object.nii.gz" not in inputs["input"]
            return {"output": "请从工作站上传。", "intermediate_steps": []}

    monkeypatch.setattr(agent_module, "create_agent", lambda **_: FakeAgent())
    with TestClient(app) as client:
        response = client.post(
            "/api/agent/chat",
            json={
                "session_id": "attachment-security",
                "user_message": ".",
                "attachment": {
                    "filename": "patient-study.nii.gz",
                    "medical_image": True,
                    "object_key": "ct/private-object.nii.gz",
                },
            },
        )

    assert response.status_code == 200
    assert "private-object" not in response.text


def test_chat_context_cannot_replace_a_server_image_source_with_a_path(monkeypatch):
    import martin.agent.agent as agent_module
    from martin.agent.case_context import CaseContext

    class FakeAgent:
        case_context = CaseContext()

        def invoke(self, inputs):
            return {"output": "收到。", "intermediate_steps": []}

    monkeypatch.setattr(agent_module, "create_agent", lambda **_: FakeAgent())
    with TestClient(app) as client:
        response = client.post(
            "/api/agent/chat",
            json={
                "session_id": "context-security",
                "user_message": "你好",
                "case_context": {"image_info": {"image_path": "C:\\private\\scan.nii.gz"}},
            },
        )

    assert response.status_code == 200
    assert "private" not in response.text


def test_historical_session_response_redacts_the_minio_reference(monkeypatch):
    import martin.agent.sessions as sessions_module

    class FakeSessionManager:
        def __init__(self, _):
            pass

        def get_case_context(self, thread_id):
            assert thread_id == "historic-viewer"
            return {
                "image_info": {
                    "modality": "胸部CT",
                    "filename": "patient-study.nii.gz",
                    "source_type": "minio_object",
                    "object_name": "ct/private-object.nii.gz",
                    "image_path": "ct/private-object.nii.gz",
                },
                "detection_completed": True,
                "nodules": [],
            }

        def get_messages(self, thread_id):
            return []

    monkeypatch.setattr(sessions_module, "SessionManager", FakeSessionManager)
    monkeypatch.setattr(sessions_module, "get_default_checkpointer", lambda: object())

    with TestClient(app) as client:
        response = client.get("/api/sessions/historic-viewer")

    assert response.status_code == 200
    assert response.json()["case_context"]["image_info"]["filename"] == "patient-study.nii.gz"
    assert "private-object" not in response.text
    assert "object_name" not in response.text
    assert "image_path" not in response.text


def test_chat_endpoint_hides_model_connection_error(monkeypatch):
    """模型网络异常不应以底层 Connection error 形式暴露给前端。"""
    import martin.agent.agent as agent_module

    class FakeAgent:
        case_context = None

        def invoke(self, inputs):
            return {"output": "错误: Agent 执行失败: Connection error.", "intermediate_steps": []}

    monkeypatch.setattr(agent_module, "create_agent", lambda **_: FakeAgent())

    with TestClient(app) as client:
        response = client.post(
            "/api/agent/chat",
            json={"session_id": "connection-error", "user_message": "你好", "case_context": {}},
        )

    assert response.status_code == 502
    assert "模型服务不可达" in response.json()["detail"]
    assert "Connection error" not in response.json()["detail"]


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
