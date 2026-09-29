"""Thread IDs are server-created and bound to the logged-in doctor."""

import uuid

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver
from starlette.websockets import WebSocketDisconnect

from martin.db import connect


def _login(client, doctor="a"):
    response = client.post(
        "/api/auth/login",
        json={
            "username": f"doctor_{doctor}",
            "password": f"TestDoctor{doctor.upper()}!2026",
        },
    )
    assert response.status_code == 200


def test_server_creates_thread_uuid(entity_client, entity_db):
    _login(entity_client)
    response = entity_client.post("/api/threads", json={"case_id": "C001"})
    assert response.status_code == 200
    thread_id = response.json()["thread_id"]
    uuid.UUID(thread_id)
    with connect(entity_db) as connection:
        row = connection.execute(
            "SELECT doctor_id, case_id FROM threads WHERE id = ?", (thread_id,)
        ).fetchone()
    assert tuple(row) == ("D001", "C001")


def test_arbitrary_thread_id_cannot_be_used(entity_client):
    _login(entity_client)
    response = entity_client.post(
        "/api/agent/chat",
        json={"session_id": str(uuid.uuid4()), "user_message": "test"},
    )
    assert response.status_code == 404


def test_other_doctor_cannot_use_thread(entity_client):
    _login(entity_client)
    thread_id = entity_client.post(
        "/api/threads", json={"case_id": "C001"}
    ).json()["thread_id"]
    _login(entity_client, "b")
    response = entity_client.post(
        "/api/agent/chat", json={"session_id": thread_id, "user_message": "test"}
    )
    assert response.status_code == 403


def test_websocket_rejects_unknown_thread(entity_client):
    _login(entity_client)
    with pytest.raises(WebSocketDisconnect) as error:
        with entity_client.websocket_connect(f"/api/ws/agent/{uuid.uuid4()}"):
            pass
    assert error.value.code == 1008


def test_other_doctor_cannot_delete_thread(entity_client):
    _login(entity_client)
    thread_id = entity_client.post(
        "/api/threads", json={"case_id": "C001"}
    ).json()["thread_id"]
    _login(entity_client, "b")
    assert entity_client.delete(f"/api/threads/{thread_id}").status_code == 403


def test_delete_thread_api_removes_checkpoint(entity_client, entity_db, tmp_path, monkeypatch):
    _login(entity_client)
    thread_id = entity_client.post(
        "/api/threads", json={"case_id": "C001"}
    ).json()["thread_id"]
    with SqliteSaver.from_conn_string(str(tmp_path / "sessions.sqlite")) as saver:
        monkeypatch.setattr("martin.agent.sessions.get_default_checkpointer", lambda: saver)
        response = entity_client.delete(f"/api/threads/{thread_id}")
        assert response.status_code == 200
        assert saver.get_tuple({"configurable": {"thread_id": thread_id}}) is None
    with connect(entity_db) as connection:
        assert connection.execute(
            "SELECT 1 FROM threads WHERE id = ?", (thread_id,)
        ).fetchone() is None


def test_delete_thread_api_reports_saver_failure(entity_client, entity_db, monkeypatch):
    class FailingSaver:
        def delete_thread(self, _thread_id):
            raise OSError("synthetic saver failure")

    _login(entity_client)
    thread_id = entity_client.post(
        "/api/threads", json={"case_id": "C001"}
    ).json()["thread_id"]
    monkeypatch.setattr(
        "martin.agent.sessions.get_default_checkpointer", lambda: FailingSaver()
    )
    response = entity_client.delete(f"/api/threads/{thread_id}")
    assert response.status_code == 503
    with connect(entity_db) as connection:
        assert connection.execute(
            "SELECT 1 FROM threads WHERE id = ?", (thread_id,)
        ).fetchone() is not None
