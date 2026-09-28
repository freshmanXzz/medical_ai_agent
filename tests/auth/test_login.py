"""Cookie login uses Argon2id and server-side token hashes."""

import hashlib

from martin.db import connect


def test_login_sets_httponly_cookie(entity_client, entity_db):
    response = entity_client.post(
        "/api/auth/login",
        json={"username": "doctor_a", "password": "TestDoctorA!2026"},
    )
    assert response.status_code == 200
    assert response.json()["id"] == "D001"
    cookie = response.headers["set-cookie"]
    assert "httponly" in cookie.lower()
    assert "samesite=lax" in cookie.lower()
    token = entity_client.cookies.get("martin_session")
    assert token
    with connect(entity_db) as connection:
        row = connection.execute("SELECT token_hash FROM auth_sessions").fetchone()
    assert row["token_hash"] == hashlib.sha256(token.encode()).hexdigest()
    assert token != row["token_hash"]


def test_invalid_password_rejected(entity_client):
    response = entity_client.post(
        "/api/auth/login", json={"username": "doctor_a", "password": "wrong"}
    )
    assert response.status_code == 401
    assert "martin_session" not in response.headers.get("set-cookie", "")
