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
    monkeypatch.setitem(agent_module.AgentExecutor._context_cache, "detection-session", case_context)
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
