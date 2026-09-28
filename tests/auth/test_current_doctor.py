"""Doctor identity comes from server session rather than request data."""


def test_request_without_cookie_is_401(entity_client):
    assert entity_client.get("/api/auth/me").status_code == 401
    assert entity_client.post("/api/threads", json={"case_id": "C001"}).status_code == 401
    assert entity_client.post(
        "/api/agent/chat", json={"session_id": "anything", "user_message": "test"}
    ).status_code == 401


def test_current_doctor_comes_from_server_session(entity_client):
    login = entity_client.post(
        "/api/auth/login",
        json={"username": "doctor_a", "password": "TestDoctorA!2026"},
    )
    assert login.status_code == 200
    me = entity_client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["id"] == "D001"
    assert "password_hash" not in me.text


def test_body_doctor_id_is_ignored_or_rejected(entity_client):
    entity_client.post(
        "/api/auth/login",
        json={"username": "doctor_b", "password": "TestDoctorB!2026"},
    )
    response = entity_client.post(
        "/api/threads", json={"case_id": "C001", "doctor_id": "D001"}
    )
    assert response.status_code == 403
