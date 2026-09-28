"""Thread IDs are server-created and bound to the logged-in doctor."""

import uuid

import pytest
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
