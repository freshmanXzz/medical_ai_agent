"""Case access always follows Case -> Patient -> doctor grant."""

from types import SimpleNamespace

from martin.db import transaction
from martin.repositories.access import AccessRepository


def _login(client, doctor):
    response = client.post(
        "/api/auth/login",
        json={
            "username": f"doctor_{doctor}",
            "password": f"TestDoctor{doctor.upper()}!2026",
        },
    )
    assert response.status_code == 200


def test_case_owner_can_read_multiple_cases(entity_client):
    _login(entity_client, "a")
    assert entity_client.get("/api/cases/C001").status_code == 200
    assert entity_client.get("/api/cases/C002").status_code == 200
    response = entity_client.get("/api/patients/P001/cases")
    assert [case["id"] for case in response.json()] == ["C001", "C002"]


def test_other_doctor_cannot_read_case_by_modified_url(entity_client):
    _login(entity_client, "b")
    assert entity_client.get("/api/cases/C001").status_code == 403
    assert entity_client.get("/api/cases/C002").status_code == 403
    assert entity_client.get("/api/cases/C003").status_code == 200
    assert entity_client.get("/api/cases/missing").status_code == 404


def test_read_only_grant_cannot_create_thread(entity_client, entity_db):
    with transaction(entity_db) as connection:
        AccessRepository(connection).grant("D002", "P001", access_level="read_only")
    _login(entity_client, "b")
    assert entity_client.get("/api/cases/C001").status_code == 200
    assert entity_client.post("/api/threads", json={"case_id": "C001"}).status_code == 403


def test_revoked_case_access_blocks_existing_thread(entity_client, entity_db):
    _login(entity_client, "a")
    thread_id = entity_client.post(
        "/api/threads", json={"case_id": "C001"}
    ).json()["thread_id"]
    with transaction(entity_db) as connection:
        AccessRepository(connection).revoke("D001", "P001")
    assert entity_client.get(f"/api/threads/{thread_id}").status_code == 403
    assert entity_client.get(f"/api/sessions/{thread_id}").status_code == 403
    assert entity_client.post(
        "/api/agent/chat", json={"session_id": thread_id, "user_message": "test"}
    ).status_code == 403
    assert entity_client.post(
        "/api/image/analyze", json={"session_id": thread_id}
    ).status_code == 403
    assert entity_client.get(
        f"/api/sessions/{thread_id}/viewer/manifest"
    ).status_code == 403


def test_session_list_filters_other_doctors_threads(entity_client, monkeypatch):
    import martin.agent.sessions as sessions_module

    _login(entity_client, "a")
    a_thread = entity_client.post(
        "/api/threads", json={"case_id": "C001"}
    ).json()["thread_id"]
    _login(entity_client, "b")
    b_thread = entity_client.post(
        "/api/threads", json={"case_id": "C003"}
    ).json()["thread_id"]

    class FakeManager:
        def __init__(self, _):
            pass

        def list_sessions(self):
            return [
                SimpleNamespace(
                    thread_id=thread_id,
                    title="Synthetic",
                    created_at="now",
                    updated_at="now",
                )
                for thread_id in (a_thread, b_thread)
            ]

    monkeypatch.setattr(sessions_module, "SessionManager", FakeManager)
    monkeypatch.setattr(sessions_module, "get_default_checkpointer", lambda: object())
    _login(entity_client, "a")
    response = entity_client.get("/api/sessions")
    assert response.status_code == 200
    assert [item["thread_id"] for item in response.json()["sessions"]] == [a_thread]
