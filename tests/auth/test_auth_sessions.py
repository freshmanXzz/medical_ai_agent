"""Session revocation and expiry."""

from datetime import datetime, timedelta, timezone

from martin.auth.session_service import SessionService
from martin.db import connect, transaction


def test_logout_revokes_session(entity_client, entity_db):
    entity_client.post(
        "/api/auth/login",
        json={"username": "doctor_a", "password": "TestDoctorA!2026"},
    )
    token = entity_client.cookies.get("martin_session")
    assert entity_client.post("/api/auth/logout").status_code == 200
    assert entity_client.get("/api/auth/me").status_code == 401
    assert SessionService(entity_db).authenticate(token) is None
    with connect(entity_db) as connection:
        assert connection.execute("SELECT revoked_at FROM auth_sessions").fetchone()[0]


def test_expired_session_is_rejected(entity_client, entity_db):
    entity_client.post(
        "/api/auth/login",
        json={"username": "doctor_a", "password": "TestDoctorA!2026"},
    )
    with transaction(entity_db) as connection:
        connection.execute(
            "UPDATE auth_sessions SET expires_at = ?",
            ((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),),
        )
    assert entity_client.get("/api/auth/me").status_code == 401
